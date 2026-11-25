"""Connect one Studio broadcast screen to the Chzzk input queue."""

import asyncio
import os
import secrets
from collections import deque
from http.cookies import SimpleCookie
from ipaddress import ip_address
from uuid import uuid4

import aiohttp
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from .proxy_handler import ProxyHandler
from .proxy_message_queue import ProxyMessageQueue
from .studio_auth import COOKIE
from .studio_broadcast_context import BROADCAST_TOKEN_HEADER
from .studio_registry import WORKSPACE_COOKIE


HISTORY_REQUESTS = {"create-new-history", "fetch-and-set-history"}
MAX_PENDING = 100


class StudioBroadcast:
    def __init__(self, server_url: str) -> None:
        self.server_url = server_url
        self.token = os.getenv("STUDIO_CHZZK_TOKEN", "")
        self.session: BroadcastSession | None = None
        self.pending: deque[dict] = deque(maxlen=MAX_PENDING)
        self.changed = asyncio.Event()
        self.channel_id = ""

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
                channel = data.get("channel_id")
                if isinstance(channel, str) and 0 < len(channel) <= 128:
                    self.channel_id = channel
                self.pending.append(
                    {
                        "type": "text-input",
                        "source": data["source"],
                        "text": text,
                        "author": author,
                        "amount": data.get("amount"),
                        "text_stream": True,
                        "require_spoken_response": True,
                        "studio_broadcast": {
                            "channel_id": self.channel_id or "local-broadcast",
                            "event_id": uuid4().hex,
                            "viewer_id": data.get("user_id"),
                            "room": False,
                        },
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

    def _headers(self) -> dict[str, str]:
        cookies = SimpleCookie()
        for name in (COOKIE, WORKSPACE_COOKIE):
            if value := self.screen.cookies.get(name):
                cookies[name] = value
        headers = {"Cookie": cookies.output(header="", sep=";").strip()}
        headers[BROADCAST_TOKEN_HEADER] = self.broadcast.token
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
                    if kind == "apply-studio-persona":
                        self.profile_applied = False
                        self.history_loaded = False
                        self.message_queue.clear()
                    await self.forward_to_server(data)
            elif kind == "text-input" and self.ready:
                self.message_queue.queue_message(
                    {
                        **data,
                        "studio_broadcast": {
                            "channel_id": self.broadcast.channel_id
                            or "local-broadcast",
                            "event_id": uuid4().hex,
                            "room": True,
                        },
                    },
                    "screen",
                )
            elif kind in {"interrupt-signal", "frontend-playback-complete"}:
                async with self.message_queue.lock:
                    if self.message_queue.matches_active(data.get("request_id")):
                        if kind == "frontend-playback-complete":
                            # The conversation engine waits for an untagged acknowledgement.
                            data.pop("request_id")
                        await self.forward_to_server(data)
                        if kind == "interrupt-signal":
                            self.message_queue.conversation_active = False
            elif kind == "fetch-history-list" and self.profile_applied:
                await self.forward_to_server(data)

    async def _consume_chzzk(self) -> None:
        while True:
            await self.broadcast.changed.wait()
            self.broadcast.changed.clear()
            while self.ready and self.broadcast.pending:
                await self._handle_text_input(
                    self.broadcast.pending.popleft(), "collector"
                )

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
        if kind == "user-input-transcription":
            message = {
                key: value
                for key, value in message.items()
                if key != "studio_broadcast"
            }
        if kind == "studio-persona-applied":
            self.profile_applied = True
        if self.profile_applied and kind in {"new-history-created", "history-data"}:
            self.history_loaded = True
        await self.screen.send_json(message)
        if self.history_loaded and kind in {
            "new-history-created",
            "history-data",
            "history-error",
        }:
            self.ready = True
            self.message_queue.set_dispatch_enabled(True)
            self.broadcast.changed.set()
