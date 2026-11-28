"""Queue proxy messages and track the active conversation."""

import asyncio
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger


CONVERSATION_TIMEOUT_SECONDS = 30
ForwardMessage = Callable[[dict[str, Any], str | None], Awaitable[None]]


class ProxyMessageQueue:
    """Dispatch one queued message at a time and recover from missing end signals."""

    def __init__(
        self,
        *,
        turn_timeout: float = CONVERSATION_TIMEOUT_SECONDS,
        max_pending: int | None = None,
    ) -> None:
        """Initialize the pending queue and conversation state."""
        self.message_queue: deque[tuple[dict[str, Any], str | None]] = deque()
        self._deadline: float | None = None
        self._request_id: str | None = None
        self.lock = asyncio.Lock()
        self._changed = asyncio.Event()
        self._consumer_task: asyncio.Task[None] | None = None
        self._forward_func: ForwardMessage | None = None
        self.turn_timeout = turn_timeout
        self.max_pending = max_pending
        self.dispatch_enabled = True

    def set_dispatch_enabled(self, enabled: bool) -> None:
        self.dispatch_enabled = enabled
        self._changed.set()
        self._ensure_consumer_running()

    def initialize(self, forward_func: ForwardMessage) -> None:
        """Set the async callback used to forward a message and its sender ID."""
        self._forward_func = forward_func
        self._ensure_consumer_running()

    def queue_message(
        self,
        message: dict[str, Any],
        sender_id: str | None = None,
        *,
        priority: bool = False,
    ) -> bool:
        """Queue a message and its sender ID, inserting at the front for priority."""
        queue_item = (message, sender_id)
        if self.max_pending is not None and len(self.message_queue) >= self.max_pending:
            if not priority:
                return False
            self.message_queue.pop()
        if priority:
            self.message_queue.appendleft(queue_item)
        else:
            self.message_queue.append(queue_item)
        self._changed.set()
        self._ensure_consumer_running()
        return True

    def discard_pending(self, matches: Callable[[dict], bool]) -> None:
        self.message_queue = deque(
            item for item in self.message_queue if not matches(item[0])
        )

    @property
    def conversation_active(self) -> bool:
        """Return whether the queue is waiting for the current turn to finish."""
        return self._deadline is not None

    @conversation_active.setter
    def conversation_active(self, active: bool) -> None:
        """Set or release the conversation lock."""
        if active:
            self._deadline = asyncio.get_running_loop().time() + self.turn_timeout
        else:
            self._deadline = None
            self._request_id = None
        self._changed.set()

    def complete_conversation(self, request_id: str | None) -> None:
        """Release the queue lock for a matching turn or an untagged group turn."""
        if request_id is None or request_id == self._request_id:
            self.conversation_active = False

    def matches_active(self, request_id: object) -> bool:
        return self._request_id is not None and request_id == self._request_id

    def has_pending_messages(self) -> bool:
        """Return whether the queue contains pending messages."""
        return bool(self.message_queue)

    def _ensure_consumer_running(self) -> None:
        """Start a consumer if forwarding is configured and messages are pending."""
        if (
            self._forward_func
            and self.dispatch_enabled
            and self.has_pending_messages()
            and (self._consumer_task is None or self._consumer_task.done())
        ):
            self._consumer_task = asyncio.create_task(self._consume_loop())

    async def _consume_loop(self) -> None:
        """Wait for queue updates or the active conversation deadline."""
        while True:
            async with self.lock:
                if not self.dispatch_enabled:
                    return
                self._changed.clear()
                remaining = None
                if self._deadline is not None:
                    remaining = self._deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        logger.warning("Proxy conversation timed out; releasing queue")
                        self.conversation_active = False

                if not self.conversation_active:
                    if not self.has_pending_messages():
                        return
                    await self.dispatch_next()
                    continue

            try:
                await asyncio.wait_for(self._changed.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass

    async def dispatch_next(self) -> None:
        """Dispatch the first pending message while the caller holds the queue lock."""
        if (
            not self.dispatch_enabled
            or self.conversation_active
            or not self.message_queue
            or not self._forward_func
        ):
            return

        message, sender_id = self.message_queue.popleft()
        request_id = message.get("request_id")
        if not isinstance(request_id, str) or not 0 < len(request_id) <= 128:
            request_id = uuid.uuid4().hex
            message = {**message, "request_id": request_id}

        self._request_id = request_id
        self.conversation_active = True
        try:
            await asyncio.wait_for(
                self._forward_message(self._forward_func, message, sender_id),
                timeout=CONVERSATION_TIMEOUT_SECONDS,
            )
        except Exception as error:
            logger.error("Failed to forward queued proxy message: {}", error)
            self.complete_conversation(request_id)

    async def _forward_message(
        self,
        forward_func: ForwardMessage,
        message: dict[str, Any],
        sender_id: str | None,
    ) -> None:
        """Forward the existing transcription notification before the original input."""
        if message.get("type") == "text-input":
            await forward_func(
                {**message, "type": "user-input-transcription"}, sender_id
            )
        await forward_func(message, sender_id)

    def stop(self) -> None:
        """Cancel the consumer and release the conversation lock."""
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
        self._consumer_task = None
        self.conversation_active = False

    def clear(self) -> None:
        """Clear all pending messages."""
        self.message_queue.clear()
