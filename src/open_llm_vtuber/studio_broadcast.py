"""Connect one Studio broadcast screen to the Chzzk input queue."""

import asyncio
import json
import os
import re
import secrets
import unicodedata
from collections import deque
from http.cookies import SimpleCookie
from ipaddress import ip_address

import aiohttp
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from .proxy_handler import ProxyHandler
from .proxy_message_queue import ProxyMessageQueue
from .studio_auth import COOKIE
from .studio_registry import WORKSPACE_COOKIE


HISTORY_REQUESTS = {"create-new-history", "fetch-and-set-history"}
MAX_PENDING = 100
CHAT_SLOTS = 5
CHAT_TTL_SECONDS = 15
REACTION_CHARACTERS = frozenset(unicodedata.normalize("NFKC", "ㅋㅎㅠㅜ"))
BROADCAST_FEEDBACK = re.compile(
    r"(?:소리|음성|마이크|볼륨|화면|영상|방송).{0,16}"
    r"(?:안\s*(?:들|보|나)|작아|작게|작습니다|커요|큽니다|멈|끊|깨져|밀려)"
)
QUESTION_OR_REQUEST = re.compile(
    r"[?？]|(?:^|\s)(?:언제|어디|왜|뭐|무엇|어떻게|몇|누구|얼마)"
    r"|(?:나요|까요|인가요|줘요?|주세요|해\s*봐|부탁해)[.!~\s]*$"
)


def _chat_priority(text: str) -> int:
    if not any(char.isalnum() and char not in REACTION_CHARACTERS for char in text):
        return 0
    if BROADCAST_FEEDBACK.search(text):
        return 3
    if QUESTION_OR_REQUEST.search(text):
        return 2
    return 1


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
                        "source": data["source"],
                        "text": text,
                        "author": author,
                        "amount": data.get("amount"),
                        "text_stream": True,
                        "require_spoken_response": True,
                        "_received_at": asyncio.get_running_loop().time(),
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
        self.chat_candidates: list[tuple[int, float, dict, str]] = []
        self.recent_chats: deque[tuple[tuple[str, str], float]] = deque(
            maxlen=MAX_PENDING
        )
        self.message_queue = ProxyMessageQueue(
            turn_timeout=95, max_pending=MAX_PENDING, take_fallback=self._take_chat_turn
        )
        self.message_queue.set_dispatch_enabled(False)

    def _expire_chat_candidates(self, now: float) -> None:
        self.chat_candidates[:] = [
            item for item in self.chat_candidates if now - item[1] < CHAT_TTL_SECONDS
        ]

    def _queue_chzzk_chat(self, message: dict, client_id: str) -> None:
        now = asyncio.get_running_loop().time()
        received_at = message["_received_at"]
        self._expire_chat_candidates(now)
        if now - received_at >= CHAT_TTL_SECONDS:
            return
        text = " ".join(unicodedata.normalize("NFKC", message["text"]).split())
        priority = _chat_priority(text)
        key = (message["author"], text.casefold())
        if not priority or any(
            key == previous and now - timestamp < CHAT_TTL_SECONDS
            for previous, timestamp in self.recent_chats
        ):
            return
        self.recent_chats.append((key, received_at))
        self.chat_candidates.append((priority, received_at, message, client_id))
        self.chat_candidates.sort(key=lambda item: item[:2], reverse=True)
        del self.chat_candidates[CHAT_SLOTS:]
        if priority >= 2:
            self.message_queue.notify_pending()

    def _take_chat_turn(self) -> tuple[dict, str] | None:
        self._expire_chat_candidates(asyncio.get_running_loop().time())
        if not self.chat_candidates or self.chat_candidates[0][0] < 2:
            return None

        priority, _, first, client_id = self.chat_candidates[0]
        if priority == 3:
            self.chat_candidates.pop(0)
        elif sum(priority >= 2 for priority, *_ in self.chat_candidates) > 1:
            candidates = [
                {"author": message["author"], "text": message["text"]}
                for _, _, message, _ in self.chat_candidates
            ]
            self.chat_candidates.clear()
            first = {
                **first,
                "text": (
                    "아래는 시청자 채팅 후보입니다. 방송 흐름에 맞는 질문이나 "
                    "요청 하나를 골라 짧게 답하세요. 같은 답으로 자연스럽게 "
                    "해결되는 질문만 함께 다루세요.\n"
                    + json.dumps(candidates, ensure_ascii=False)
                ),
            }
        else:
            self.chat_candidates.pop(0)
        return first, client_id

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
                    if kind == "apply-studio-persona":
                        self.profile_applied = False
                        self.history_loaded = False
                        self.message_queue.clear()
                        self.chat_candidates.clear()
                        self.recent_chats.clear()
                    await self.forward_to_server(data)
            elif kind == "text-input" and self.ready:
                self.message_queue.queue_message(data, "screen")
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
                message = self.broadcast.pending.popleft()
                if message["source"] == "chzzk_chat" and (
                    asyncio.get_running_loop().time() - message["_received_at"]
                    >= CHAT_TTL_SECONDS
                ):
                    continue
                await self._handle_text_input(message, "collector")

    async def forward_to_server(
        self, message: dict, sender_id: str | None = None
    ) -> None:
        if self.server_ws is None or self.server_ws.closed:
            raise aiohttp.ClientConnectionError("Studio broadcast connection closed")
        if message.get("type") != "user-input-transcription":
            await self.server_ws.send_json(
                {key: value for key, value in message.items() if key != "_received_at"}
            )

    async def broadcast_to_clients(
        self, message: dict, exclude_client: str | None = None
    ) -> None:
        kind = message.get("type")
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
