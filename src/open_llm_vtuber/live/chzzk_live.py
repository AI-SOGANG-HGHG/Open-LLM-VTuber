"""Chzzk Live streaming platform integration client."""

import asyncio
from collections.abc import Callable
import json
import time
import traceback
from typing import Any

import aiohttp
from loguru import logger
import websockets

from .live_interface import LivePlatformInterface

# Chzzk WebSocket protocol command constants
CHZZK_CMD_PING = 0
CHZZK_CMD_PONG = 10000
CHZZK_CMD_CONNECT = 100
CHZZK_CMD_CONNECTED = 10100
CHZZK_CMD_CHAT = 93101
CHZZK_CMD_DONATION = 93102


class ChzzkLivePlatform(LivePlatformInterface):
    """Implementation of LivePlatformInterface for the Chzzk Live platform.

    Connects to a Chzzk live chat room in read-only mode, collects real-time
    chat (cmd 93101) and cheese donation (cmd 93102) events, and forwards them
    as standardized JSON payloads to the local VTuber `/proxy-ws` endpoint.
    """

    def __init__(
        self,
        channel_id: str,
        proxy_url: str = "ws://localhost:12393/proxy-ws",
    ) -> None:
        """Initialize the Chzzk Live platform client.

        Args:
            channel_id: The 32-character Chzzk channel ID hash.
            proxy_url: The WebSocket URL of the local VTuber proxy endpoint.
        """
        self._channel_id: str = channel_id.strip()
        self._proxy_url: str = proxy_url
        self._session: aiohttp.ClientSession | None = None
        self._proxy_ws: Any = None
        self._chzzk_ws: aiohttp.ClientWebSocketResponse | None = None
        self._connected: bool = False
        self._running: bool = False
        self._message_handlers: list[Callable[[dict[str, Any]], None]] = []

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected to the local proxy.

        Returns:
            bool: True if connected to the proxy WebSocket, False otherwise.
        """
        try:
            if not self._connected or self._proxy_ws is None:
                return False
            if hasattr(self._proxy_ws, "closed"):
                return not bool(self._proxy_ws.closed)
            if hasattr(self._proxy_ws, "open"):
                return bool(self._proxy_ws.open)
            return True
        except Exception:
            return False

    async def connect(self, proxy_url: str) -> bool:
        """Connect to the local VTuber proxy WebSocket server.

        Args:
            proxy_url: The WebSocket URL of the proxy endpoint.

        Returns:
            bool: True if connection succeeded, False otherwise.
        """
        try:
            self._proxy_ws = await websockets.connect(
                proxy_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )
            self._connected = True
            logger.info(f"[ChzzkLive] Connected to VTuber proxy at {proxy_url}")
            return True
        except Exception as e:
            logger.error(f"[ChzzkLive] Failed to connect to proxy ({proxy_url}): {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the Chzzk chat room and local proxy server."""
        self._running = False

        if self._chzzk_ws and not self._chzzk_ws.closed:
            try:
                await self._chzzk_ws.close()
            except Exception as e:
                logger.warning(f"[ChzzkLive] Error while closing Chzzk WebSocket: {e}")
            self._chzzk_ws = None

        if self._proxy_ws:
            try:
                await self._proxy_ws.close()
            except Exception as e:
                logger.warning(f"[ChzzkLive] Error while closing proxy WebSocket: {e}")
            self._proxy_ws = None

        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"[ChzzkLive] Error while closing HTTP session: {e}")
            self._session = None

        self._connected = False
        logger.info("[ChzzkLive] Disconnected from Chzzk Live and proxy server")

    async def send_message(self, text: str) -> bool:
        """Send a message to the live platform.

        Not used in read-only mode because the client only monitors incoming
        viewer chat and donations.

        Args:
            text: The message text content.

        Returns:
            bool: Always returns False in read-only mode.
        """
        logger.warning(
            f"[ChzzkLive] Sending message back to Chzzk chat is unsupported: {text}"
        )
        return False

    async def register_message_handler(
        self, handler: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a callback function to handle messages from the VTuber proxy.

        Args:
            handler: Callback accepting a parsed message dictionary.
        """
        self._message_handlers.append(handler)
        logger.debug("[ChzzkLive] Registered new proxy message handler")

    async def handle_incoming_messages(self, message: dict[str, Any]) -> None:
        """Process incoming messages broadcast from the VTuber proxy server.

        Args:
            message: The message dictionary received from the proxy.
        """
        for handler in self._message_handlers:
            try:
                await asyncio.to_thread(handler, message)
            except Exception as e:
                logger.error(f"[ChzzkLive] Error in message handler: {e}")

    async def start_receiving(self) -> None:
        """Receive broadcast messages from the local proxy WebSocket in a loop."""
        if not self.is_connected:
            logger.error("[ChzzkLive] Cannot start receiving: Not connected to proxy")
            return

        try:
            logger.info("[ChzzkLive] Started receiving messages from proxy")
            while self._running and self.is_connected:
                try:
                    raw_message = await self._proxy_ws.recv()
                    data = json.loads(raw_message)
                    await self.handle_incoming_messages(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(
                        "[ChzzkLive] Proxy WebSocket connection closed by server"
                    )
                    self._connected = False
                    break
                except Exception as e:
                    logger.error(f"[ChzzkLive] Error receiving message from proxy: {e}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.debug("[ChzzkLive] Proxy receive loop cancelled")

    async def _fetch_chat_channel_info(self) -> tuple[str, str]:
        """Fetch the active chatChannelId and accessToken from Chzzk polling APIs.

        Returns:
            tuple[str, str]: A tuple of (chat_channel_id, access_token).

        Raises:
            RuntimeError: If the HTTP session is uninitialized, the API request
                fails, or the target channel does not have an active chat room.
        """
        if self._session is None:
            raise RuntimeError("HTTP session is not initialized")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
        status_url = (
            "https://api.chzzk.naver.com/polling/v2/channels/"
            f"{self._channel_id}/live-status"
        )
        async with self._session.get(status_url, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"Failed to fetch Chzzk live-status (HTTP {resp.status})"
                )
            status_data: dict[str, Any] = await resp.json()

        content: dict[str, Any] = status_data.get("content") or {}
        chat_channel_id: str | None = content.get("chatChannelId")
        live_status: str | None = content.get("status")

        if not chat_channel_id:
            raise RuntimeError(
                f"chatChannelId not found (live status: {live_status}). "
                "Verify that the channel ID is valid and the stream is active."
            )

        token_url = (
            "https://comm-api.game.naver.com/nng_main/v1/chats/access-token"
            f"?channelId={chat_channel_id}&chatType=STREAMING"
        )
        async with self._session.get(token_url, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"Failed to fetch Chzzk access-token (HTTP {resp.status})"
                )
            token_data: dict[str, Any] = await resp.json()

        token_content: dict[str, Any] = token_data.get("content") or {}
        access_token: str = token_content.get("accessToken") or ""
        return chat_channel_id, access_token

    async def _forward_to_proxy(self, payload: dict[str, Any]) -> bool:
        """Forward a standardized chat or donation payload to the local proxy.

        Args:
            payload: Standardized message dictionary containing source, author,
                text, amount, priority, and timestamp.

        Returns:
            bool: True if the payload was sent successfully, False otherwise.
        """
        if not self.is_connected or self._proxy_ws is None:
            logger.error("[ChzzkLive] Cannot forward message: Not connected to proxy")
            return False

        try:
            await self._proxy_ws.send(json.dumps(payload, ensure_ascii=False))
            logger.info(
                f"[ChzzkLive -> Proxy] ({payload['source']}) "
                f"{payload['author']}: {payload['text']} "
                f"(amount={payload['amount']})"
            )
            return True
        except Exception as e:
            logger.error(f"[ChzzkLive] Error sending payload to proxy: {e}")
            self._connected = False
            return False

    async def _parse_and_forward_event(
        self, cmd: int, body_items: list[dict[str, Any]]
    ) -> None:
        """Parse Chzzk chat (93101) or donation (93102) items and forward them.

        Args:
            cmd: The Chzzk WebSocket command integer (93101 or 93102).
            body_items: List of raw event dictionaries from the packet `bdy` field.
        """
        for item in body_items:
            try:
                text = str(item.get("msg") or "").strip()
                if not text:
                    continue

                user_id = str(item.get("uid") or "anonymous")
                msg_time_ms = item.get("msgTime")
                timestamp = (
                    float(msg_time_ms) / 1000.0
                    if isinstance(msg_time_ms, (int, float))
                    else time.time()
                )

                author = "Anonymous"
                raw_profile = item.get("profile")
                if isinstance(raw_profile, str) and raw_profile:
                    try:
                        profile_obj = json.loads(raw_profile)
                        if isinstance(profile_obj, dict):
                            nickname = profile_obj.get("nickname")
                            if isinstance(nickname, str) and nickname.strip():
                                author = nickname.strip()
                    except json.JSONDecodeError:
                        pass

                amount = 0
                source = "chzzk_chat"
                priority = 3

                if cmd == CHZZK_CMD_DONATION:
                    source = "chzzk_donation"
                    raw_extras = item.get("extras")
                    if isinstance(raw_extras, str) and raw_extras:
                        try:
                            extras_obj = json.loads(raw_extras)
                            if isinstance(extras_obj, dict):
                                pay_amount = extras_obj.get("payAmount")
                                if pay_amount is not None:
                                    amount = int(pay_amount)
                        except (json.JSONDecodeError, ValueError):
                            pass
                    priority = 0 if amount >= 10000 else 2

                payload: dict[str, Any] = {
                    "type": "text-input",
                    "source": source,
                    "user_id": user_id,
                    "author": author,
                    "text": text,
                    "amount": amount,
                    "priority": priority,
                    "timestamp": timestamp,
                }
                await self._forward_to_proxy(payload)
            except Exception as e:
                logger.error(f"[ChzzkLive] Failed to parse chat item: {e}")

    async def _listen_chzzk_chat(self, chat_channel_id: str, access_token: str) -> None:
        """Connect to the Chzzk chat WebSocket and listen for live events.

        Args:
            chat_channel_id: The active Chzzk chat channel identifier.
            access_token: The read-only chat room access token.

        Raises:
            RuntimeError: If the HTTP session is not initialized.
        """
        if self._session is None:
            raise RuntimeError("HTTP session is not initialized")

        ws_url = "wss://kr-ss1.chat.naver.com/chat"
        async with self._session.ws_connect(ws_url, heartbeat=30.0) as ws:
            self._chzzk_ws = ws

            connect_packet: dict[str, Any] = {
                "ver": "2",
                "svcid": "game",
                "cid": chat_channel_id,
                "cmd": CHZZK_CMD_CONNECT,
                "tid": 1,
                "bdy": {
                    "uid": None,
                    "devType": 2001,
                    "accTkn": access_token,
                    "auth": "READ",
                },
            }
            await ws.send_json(connect_packet)
            logger.info(
                f"[ChzzkLive] Sent handshake to Chzzk chat room ({chat_channel_id})"
            )

            async for msg in ws:
                if not self._running:
                    break

                if msg.type == aiohttp.WSMsgType.TEXT:
                    packet: dict[str, Any] = json.loads(msg.data)
                    cmd = packet.get("cmd")

                    if cmd == CHZZK_CMD_PING:
                        await ws.send_json({"ver": "2", "cmd": CHZZK_CMD_PONG})
                    elif cmd == CHZZK_CMD_CONNECTED:
                        logger.info(
                            "[ChzzkLive] Successfully joined Chzzk live chat room!"
                        )
                    elif cmd in (CHZZK_CMD_CHAT, CHZZK_CMD_DONATION):
                        body = packet.get("bdy")
                        if isinstance(body, list):
                            await self._parse_and_forward_event(int(cmd), body)

                elif msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    logger.warning(
                        "[ChzzkLive] Chzzk chat WebSocket closed or encountered error"
                    )
                    break

    async def run(self) -> None:
        """Run the Chzzk Live platform client lifecycle."""
        receive_task: asyncio.Task[None] | None = None
        try:
            self._running = True
            self._session = aiohttp.ClientSession()

            if not await self.connect(self._proxy_url):
                logger.error("[ChzzkLive] Failed to connect to local proxy, exiting")
                return

            receive_task = asyncio.create_task(self.start_receiving())

            chat_channel_id, access_token = await self._fetch_chat_channel_info()
            logger.info(f"[ChzzkLive] Resolved chatChannelId={chat_channel_id}")

            await self._listen_chzzk_chat(chat_channel_id, access_token)

        except KeyboardInterrupt:
            logger.info("[ChzzkLive] Received keyboard interrupt, shutting down")
        except Exception as e:
            logger.error(f"[ChzzkLive] Error in Chzzk Live run loop: {e}")
            logger.debug(traceback.format_exc())
        finally:
            if receive_task and not receive_task.done():
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass
            await self.disconnect()
