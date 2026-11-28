"""Connect one Studio broadcast screen to the Chzzk input queue."""

import asyncio
import os
import secrets
from collections import deque
from functools import partial
from http.cookies import SimpleCookie
from ipaddress import ip_address

import aiohttp
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from .proxy_handler import ProxyHandler
from .proxy_message_queue import ProxyMessageQueue
from . import studio_audience
from .studio_audience import AudienceQuestion
from .studio_auth import COOKIE
from .studio_registry import WORKSPACE_COOKIE


HISTORY_REQUESTS = {"create-new-history", "fetch-and-set-history"}
MAX_PENDING = 100
IDLE_SPEAK_SECONDS = 10.0


class StudioBroadcast:
    def __init__(self, server_url: str) -> None:
        self.server_url = server_url
        self.token = os.getenv("STUDIO_CHZZK_TOKEN", "")
        self.session: BroadcastSession | None = None
        self.pending: deque[dict] = deque(maxlen=MAX_PENDING)
        self.changed = asyncio.Event()

    async def handle_screen(self, socket: WebSocket) -> None:
        if not self.token or not socket.cookies.get(WORKSPACE_COOKIE):
            await socket.close(code=1008)
            return
        if self.session is not None:
            await socket.close(code=1013)
            return
        session = BroadcastSession(self, socket)
        self.session = session
        try:
            await session.run()
        finally:
            self.pending.clear()
            self.session = None

    async def handle_collector(self, socket: WebSocket) -> None:
        try:
            loopback = (
                socket.client is not None and ip_address(socket.client.host).is_loopback
            )
        except ValueError:
            loopback = False
        expected = f"Bearer {self.token}".encode()
        supplied = socket.headers.get("authorization", "").encode()
        if (
            not self.token
            or not loopback
            or not secrets.compare_digest(supplied, expected)
        ):
            await socket.close(code=1008)
            return
        await socket.accept()
        try:
            while True:
                data = await socket.receive_json()
                if not isinstance(data, dict) or data.get("type") != "text-input":
                    continue
                if data.get("source") not in ("chzzk_chat", "chzzk_donation"):
                    continue
                text, author = data.get("text"), data.get("author")
                if not isinstance(text, str) or not isinstance(author, str):
                    continue
                if len(text) > 4096 or len(author) > 256:
                    continue
                self.pending.append(
                    {
                        "type": "text-input",
                        "_received_at": asyncio.get_running_loop().time(),
                        "source": data["source"],
                        "text": text,
                        "author": author,
                        "amount": data.get("amount"),
                        "text_stream": True,
                        "require_spoken_response": True,
                    }
                )
                self.changed.set()
        except (ValueError, WebSocketDisconnect):
            return


class BroadcastSession(ProxyHandler):
    def __init__(self, broadcast: StudioBroadcast, screen: WebSocket) -> None:
        super().__init__(broadcast.server_url)
        self.broadcast = broadcast
        self.screen = screen
        self.profile_applied = False
        self.history_loaded = False
        self.ready = False
        self.message_queue = ProxyMessageQueue(turn_timeout=95, max_pending=MAX_PENDING)
        self.message_queue.set_dispatch_enabled(False)
        self.opening_queued = False
        self.next_idle_at = 0.0
        self.question: AudienceQuestion | None = None
        self.topics = studio_audience.shuffled_topics()
        self.ask_on_idle = True

    def _reset_idle_timer(self) -> None:
        self.next_idle_at = asyncio.get_running_loop().time() + IDLE_SPEAK_SECONDS
        self.broadcast.changed.set()

    def _queue_proactive_speech(self, reason: str, **details) -> bool:
        queued = self.message_queue.queue_message(
            {
                "type": "ai-speak-signal",
                "broadcast_reason": reason,
                "text_stream": True,
                "require_spoken_response": True,
                **details,
            }
        )
        self._reset_idle_timer()
        return queued

    def _speak_on_idle(self) -> None:
        self.question = None
        if self.ask_on_idle:
            question = AudienceQuestion(next(self.topics))
            if self._queue_proactive_speech(
                "audience_question",
                audience_topic=question.topic,
                request_id=question.request_id,
            ):
                self.question = question
        else:
            self._queue_proactive_speech("idle")
        self.ask_on_idle = not self.ask_on_idle

    async def _collect_answer(self, received_at: float, text: str) -> bool:
        question = self.question
        if question is None or not question.collect(text, received_at):
            return False
        await self.screen.send_json(
            {
                "type": "audience-vote-counts",
                "request_id": question.request_id,
                "votes": question.votes.copy(),
            }
        )
        return True

    async def _close_question(self) -> None:
        question = self.question
        self.question = None
        self._reset_idle_timer()
        if question and question.opened_at is not None:
            await self.screen.send_json(
                {"type": "audience-question-closed", "request_id": question.request_id}
            )

    def _headers(self) -> dict[str, str]:
        cookies = SimpleCookie()
        for name in (COOKIE, WORKSPACE_COOKIE):
            if value := self.screen.cookies.get(name):
                cookies[name] = value
        headers = {"Cookie": cookies.output(header="", sep=";").strip()}
        if origin := self.screen.headers.get("origin"):
            headers["Origin"] = origin
        return headers

    async def run(self) -> None:
        await self.screen.accept()
        tasks = []
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(sock_connect=10)
            ) as session:
                async with session.ws_connect(
                    self.server_url,
                    headers=self._headers(),
                    heartbeat=20,
                ) as upstream:
                    self.server_ws = upstream
                    self.connected = True
                    self.message_queue.initialize(self.forward_with_broadcast)
                    tasks = [
                        asyncio.create_task(coro)
                        for coro in (
                            self.forward_server_messages(),
                            self._read_screen(),
                            self._consume_chzzk(),
                        )
                    ]
                    done, _ = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        task.result()
        except WebSocketDisconnect:
            pass
        except (aiohttp.ClientError, asyncio.TimeoutError):
            await self.screen.close(code=1011)
            return
        finally:
            self.connected = False
            self.message_queue.stop()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._close_screen()

    async def _close_screen(self) -> None:
        try:
            await self.screen.close(code=1012)
        except (WebSocketDisconnect, RuntimeError):
            pass

    async def _read_screen(self) -> None:
        while True:
            data = await self.screen.receive_json()
            if not isinstance(data, dict):
                continue
            kind = data.get("type")
            if not isinstance(kind, str):
                continue
            if kind in HISTORY_REQUESTS or kind == "apply-studio-persona":
                async with self.message_queue.lock:
                    if self.message_queue.conversation_active:
                        await self.screen.send_json(
                            {"type": "history-error", "code": "busy"}
                        )
                        continue
                    self.ready = False
                    self.message_queue.set_dispatch_enabled(False)
                    await self._close_question()
                    self.message_queue.discard_pending(
                        lambda item: item.get("type") == "ai-speak-signal"
                        and item.get("broadcast_reason")
                        in ("audience_question", "audience_reaction")
                    )
                    if kind == "apply-studio-persona":
                        self.profile_applied = False
                        self.history_loaded = False
                        self.message_queue.clear()
                    await self.forward_to_server(data)
            elif kind == "text-input" and self.ready:
                self._reset_idle_timer()
                text = data.get("text")
                if isinstance(text, str) and not await self._collect_answer(
                    asyncio.get_running_loop().time(), text
                ):
                    self.message_queue.queue_message(data, "screen")
            elif kind in {"interrupt-signal", "frontend-playback-complete"}:
                async with self.message_queue.lock:
                    if self.message_queue.matches_active(data.get("request_id")):
                        if kind == "frontend-playback-complete":
                            # The conversation engine waits for an untagged acknowledgement.
                            data.pop("request_id")
                        elif (
                            self.question
                            and self.question.request_id == data["request_id"]
                        ):
                            await self._close_question()
                        await self.forward_to_server(data)
                        if kind == "interrupt-signal":
                            self.message_queue.conversation_active = False
                            self._reset_idle_timer()
            elif kind == "fetch-history-list" and self.profile_applied:
                await self.forward_to_server(data)

    async def _consume_chzzk(self) -> None:
        loop = asyncio.get_running_loop()

        while True:
            for _ in range(len(self.broadcast.pending)):
                if not self.ready:
                    break
                message = self.broadcast.pending.popleft()
                received_at = message.pop("_received_at")
                self._reset_idle_timer()
                await self._handle_text_input(
                    message,
                    "collector",
                    consume_chat=partial(self._collect_answer, received_at),
                )

            wait_seconds = IDLE_SPEAK_SECONDS
            question = self.question
            if question is not None and question.closes_at is not None:
                deadline = question.closes_at
                remaining = deadline - loop.time()
                if remaining > 0:
                    wait_seconds = remaining
                elif (
                    not self.broadcast.pending
                    or self.broadcast.pending[0]["_received_at"] >= deadline
                ):
                    # Count by arrival time even when asynchronous filtering runs late.
                    if not any(question.votes) or self._queue_proactive_speech(
                        "audience_reaction",
                        audience_topic=question.topic,
                        audience_votes=question.votes.copy(),
                    ):
                        await self._close_question()
            elif question and question.opened_at is not None:
                # A timeout or urgent donation may release the queue without a turn-end.
                if not self.message_queue.matches_active(question.request_id):
                    await self._close_question()
            elif (
                self.ready
                and self.opening_queued
                and not self.broadcast.pending
                and not self.message_queue.conversation_active
                and not self.message_queue.has_pending_messages()
            ):
                remaining = self.next_idle_at - loop.time()
                if remaining <= 0:
                    self._speak_on_idle()
                else:
                    wait_seconds = remaining

            if self.ready and self.broadcast.pending:
                continue
            self.broadcast.changed.clear()
            try:
                await asyncio.wait_for(
                    self.broadcast.changed.wait(), timeout=wait_seconds
                )
            except asyncio.TimeoutError:
                continue

    async def forward_to_server(
        self, message: dict, sender_id: str | None = None
    ) -> None:
        if self.server_ws is None or self.server_ws.closed:
            raise aiohttp.ClientConnectionError("Studio broadcast connection closed")
        if message.get("type") != "user-input-transcription":
            await self.server_ws.send_json(message)

    async def broadcast_to_clients(
        self, message: dict, exclude_client: str | None = None
    ) -> None:
        kind = message.get("type")
        if kind == "studio-persona-applied":
            self.profile_applied = True
        if self.profile_applied and kind in {"new-history-created", "history-data"}:
            self.history_loaded = True
        question = self.question
        if (
            question
            and question.request_id == message.get("request_id")
            and self.message_queue.matches_active(question.request_id)
        ):
            if kind == "control" and message.get("text") == "conversation-chain-start":
                prompt, choices = studio_audience.QUESTIONS[question.topic]
                question.opened_at = asyncio.get_running_loop().time()
                message = {
                    **message,
                    "audience_question": {"text": prompt, "choices": choices},
                }
            elif kind == "control" and message.get("text") == "conversation-chain-end":
                question.closes_at = (
                    asyncio.get_running_loop().time() + studio_audience.ANSWER_SECONDS
                )
            elif kind == "error":
                await self._close_question()
        elif kind == "interrupt-signal" and question and question.closes_at is None:
            await self._close_question()
        await self.screen.send_json(message)

        if kind == "control" and message.get("text") == "conversation-chain-end":
            self._reset_idle_timer()

        if self.history_loaded and kind in {
            "new-history-created",
            "history-data",
            "history-error",
        }:
            self.ready = True

            if not self.opening_queued and kind in {
                "new-history-created",
                "history-data",
            }:
                self.opening_queued = True
                self._queue_proactive_speech("opening")

            self.message_queue.set_dispatch_enabled(True)
            self.broadcast.changed.set()
