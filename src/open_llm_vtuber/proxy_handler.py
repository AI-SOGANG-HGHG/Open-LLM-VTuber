"""Relay WebSocket messages between proxy clients and the conversation server."""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from fastapi import WebSocket
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from .proxy_message_queue import ProxyMessageQueue

try:
    from .live.chat_filter import ChatSafetyFilter
except ModuleNotFoundError as error:
    if error.name not in (
        f"{__package__}.live",
        f"{__package__}.live.chat_filter",
    ):
        raise
    try:
        from .chat_filter import ChatSafetyFilter
    except ModuleNotFoundError as fallback_error:
        if fallback_error.name != f"{__package__}.chat_filter":
            raise
        ChatSafetyFilter = None


# Match the Chzzk collector's threshold for urgent donations.
URGENT_DONATION_AMOUNT = 10_000

# Shown in place of a donation message that the safety filter blocked.
BLOCKED_DONATION_NOTICE = "후원 메시지는 필터링되어 표시되지 않습니다"


def blocked_donation_text(author: str, amount: object) -> str:
    """Build the text that replaces a blocked donation message.

    The conversation server only reads ``text``, so the sanitized nickname
    and amount are written into it to keep the donation acknowledgeable.

    Args:
        author: Nickname that already passed ``sanitize_author``.
        amount: Donation amount from the payload; ignored unless a positive int.

    Returns:
        A notice such as ``"홍길동님이 1,000치즈를 후원했습니다. (...)"``.
    """
    if type(amount) is int and amount > 0:
        return (
            f"{author}님이 {amount:,}치즈를 후원했습니다. ({BLOCKED_DONATION_NOTICE})"
        )
    return f"{author}님이 후원했습니다. ({BLOCKED_DONATION_NOTICE})"


class ProxyHandler:
    """
    A proxy handler that allows multiple clients to connect through a single WebSocket connection to the server.
    This enables scenarios like having a web client and a live platform both connected to the same VTuber server.
    """

    def __init__(self, server_url: str = "ws://localhost:12393/client-ws") -> None:
        """
        Initialize the proxy handler.

        Args:
            server_url: The WebSocket URL of the actual server
        """
        self.server_url = server_url
        self.server_ws: aiohttp.ClientWebSocketResponse | None = None
        self.clients: dict[str, WebSocket] = {}
        self.connected = False
        self.server_task: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()

        # Initialize message queue manager
        self.message_queue = ProxyMessageQueue()
        self.safety_filter = (
            ChatSafetyFilter(enable_ai_classifier=True) if ChatSafetyFilter else None
        )
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._running = True
        self._session: aiohttp.ClientSession | None = None

    async def connect_to_server(self):
        """Establish a WebSocket connection to the actual server"""
        if self.connected:
            return

        async with self.lock:
            if self.connected:  # Double-check to prevent race conditions
                return

            try:
                # Create session if not exists
                if not self._session:
                    self._session = aiohttp.ClientSession()
                self.server_ws = await self._session.ws_connect(self.server_url)
                self.connected = True
                logger.info(f"Proxy connected to server at {self.server_url}")

                # Initialize message queue with our forward function
                self.message_queue.initialize(self.forward_with_broadcast)

                # Start heartbeat task
                self._heartbeat_task = asyncio.create_task(self._maintain_connection())

                # Start task to receive messages from server
                self.server_task = asyncio.create_task(self.forward_server_messages())
            except Exception as e:
                logger.error(f"Failed to connect to server: {e}")
                if self._session:
                    await self._session.close()
                    self._session = None
                raise

    async def _maintain_connection(self):
        """Maintain connection with heartbeat and automatic reconnection"""
        while self._running:
            try:
                if self.connected and self.server_ws and not self.server_ws.closed:
                    # Send heartbeat
                    await self.server_ws.send_json({"type": "heartbeat"})
                    await asyncio.sleep(30)  # Heartbeat interval
                else:
                    # Try to reconnect
                    logger.info("Connection lost, attempting to reconnect...")
                    try:
                        await self.connect_to_server()
                    except Exception as e:
                        logger.error(f"Reconnection failed: {e}")
                        await asyncio.sleep(5)  # Wait before retry
            except Exception as e:
                logger.error(f"Error in connection maintenance: {e}")
                self.connected = False
                await asyncio.sleep(5)

    async def handle_client_connection(self, websocket: WebSocket) -> None:
        """
        Handle a new client connection to the proxy.

        Args:
            websocket: The client's WebSocket connection
        """
        await websocket.accept()

        # Generate a unique client ID
        client_id = str(uuid.uuid4())
        self.clients[client_id] = websocket
        logger.info(
            f"Client {client_id} connected to proxy. Total clients: {len(self.clients)}"
        )

        # Ensure server connection is established
        if not self.connected:
            await self.connect_to_server()

        if self.connected:
            try:
                init_request = {"type": "request-init-config", "client_id": client_id}
                await self.forward_to_server(init_request, client_id)
            except Exception as e:
                logger.error(f"Failed to request initialization: {e}")

        try:
            # Handle messages from this client
            while True:
                message = await websocket.receive_json()

                if message.get("type") == "text-input":
                    await self._handle_text_input(message, client_id)
                elif message.get("type") == "interrupt-signal":
                    async with self.message_queue.lock:
                        await self.forward_to_server(message, client_id)
                        self.message_queue.conversation_active = False
                else:
                    await self.forward_to_server(message, client_id)

        except WebSocketDisconnect:
            await self.handle_client_disconnect(client_id)
        except Exception as e:
            logger.error(f"Error handling client connection: {e}")
            await self.handle_client_disconnect(client_id)

    async def _handle_text_input(
        self,
        message: dict[str, Any],
        client_id: str,
        *,
        consume_chat: Callable[[str, str], Awaitable[bool]] | None = None,
    ) -> None:
        """Validate Chzzk input before queuing it or interrupting the current turn."""
        source = message.get("source")
        if source not in ("chzzk_chat", "chzzk_donation"):
            self.message_queue.queue_message(message, client_id)
            return

        if self.safety_filter is None:
            logger.warning(
                "Discarding Chzzk input because the chat filter is unavailable"
            )
            return

        author = message.get("author", "")
        text = message.get("text", "")
        if not isinstance(author, str) or not isinstance(text, str):
            logger.warning("Discarding Chzzk input with invalid author or text")
            return

        try:
            if hasattr(self.safety_filter, "avalidate"):
                is_safe, result = await self.safety_filter.avalidate(author, text)
            else:
                is_safe, result = self.safety_filter.validate(author, text)
        except Exception:
            logger.warning("Discarding Chzzk input because chat validation failed")
            return
        is_donation = source == "chzzk_donation"
        if is_safe:
            if not is_donation and consume_chat and await consume_chat(text, result):
                return
            message = {**message, "author": result}
        elif not is_donation:
            logger.warning(
                f"🛑 Chat safety filter blocked Chzzk input "
                f"(reason={result}) | author={author!r} | text={text!r}"
            )
            return
        else:
            # Keep the donation, but never forward the blocked body.
            try:
                safe_author = self.safety_filter.sanitize_author(author)
            except Exception:
                logger.warning("Discarding Chzzk donation because sanitizing failed")
                return
            logger.warning(
                f"Chat safety filter replaced Chzzk donation message ({result})"
            )
            message = {
                **message,
                "author": safe_author,
                "text": blocked_donation_text(safe_author, message.get("amount")),
            }

        amount = message.get("amount")
        if is_donation and type(amount) is int and amount >= URGENT_DONATION_AMOUNT:
            async with self.message_queue.lock:
                if (
                    self.message_queue.dispatch_enabled
                    and self.message_queue.conversation_active
                ):
                    await self.forward_to_server(
                        {"type": "interrupt-signal"}, client_id
                    )
                    self.message_queue.conversation_active = False
                    await self.broadcast_to_clients(
                        {"type": "interrupt-signal", "text": "conversation-interrupted"}
                    )
                self.message_queue.queue_message(message, client_id, priority=True)
                await self.message_queue.dispatch_next()
        else:
            self.message_queue.queue_message(message, client_id, priority=is_donation)

    async def handle_client_disconnect(self, client_id: str):
        """
        Handle a client disconnection.

        Args:
            client_id: The ID of the disconnected client
        """
        self.clients.pop(client_id, None)
        logger.info(
            f"Client {client_id} removed. Remaining clients: {len(self.clients)}"
        )

        # If no clients are connected, disconnect from the server
        if not self.clients and self.connected:
            await self.disconnect()

    async def disconnect(self):
        """Disconnect from the server"""
        self._running = False

        # Cancel heartbeat task
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.server_ws and not self.server_ws.closed:
            await self.server_ws.close()

        if self.server_task:
            self.server_task.cancel()

        # Close session
        if self._session:
            await self._session.close()
            self._session = None

        self.connected = False
        # Stop and clear the message queue
        self.message_queue.stop()
        self.message_queue.clear()
        logger.info("Proxy disconnected from server")

    async def forward_to_server(
        self, message: dict[str, Any], sender_id: str | None = None
    ) -> None:
        """
        Forward a message from a client to the server.

        Args:
            message: The message to forward
            sender_id: ID of the client sending the message, to exclude from broadcast
        """
        if not self.connected or not self.server_ws:
            await self.connect_to_server()

        if self.server_ws and not self.server_ws.closed:
            await self.server_ws.send_json(message)

    async def forward_server_messages(self) -> None:
        """Forward messages from server to all connected clients"""
        try:
            while self.connected and self.server_ws and not self.server_ws.closed:
                try:
                    msg = await self.server_ws.receive()

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            # Parse the message
                            if not msg.data:  # Check if data is empty
                                continue

                            data = json.loads(msg.data)
                            if not data:  # Check if parsed data is empty
                                continue

                            # Deliver the end before opening the queue for the next turn.
                            await self.broadcast_to_clients(data)
                            if (
                                data.get("type") == "control"
                                and data.get("text") == "conversation-chain-end"
                            ):
                                self.message_queue.complete_conversation(
                                    data.get("request_id")
                                )
                                logger.info("Received conversation end signal")

                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse message data: {e}")
                            continue
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {self.server_ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        break
                except Exception as e:
                    logger.error(f"Error processing server message: {e}")
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error forwarding server messages: {e}")
        finally:
            self.connected = False
            self.message_queue.conversation_active = False
            logger.info("Server message forwarding ended")

    async def broadcast_to_clients(
        self, message: dict[str, Any], exclude_client: str | None = None
    ) -> None:
        """
        Broadcast a message to all connected clients.

        Args:
            message: The message to broadcast
            exclude_client: Optional client ID to exclude from broadcast
        """
        if not message:  # Add null check
            return

        disconnected_clients = []

        # Log message, but handle audio data specially to avoid huge logs
        log_msg = (
            message.copy()
            if "audio" not in message
            else {
                **{k: v for k, v in message.items() if k != "audio"},
                "audio": f"[Audio data, {len(message.get('audio') or '')} bytes truncated]",
            }
        )

        if "volumes" in log_msg and len(log_msg.get("volumes") or []) > 10:
            log_msg["volumes"] = f"[{len(message.get('volumes') or [])} volume values]"

        logger.debug(f"Broadcasting to clients (excluding {exclude_client}): {log_msg}")

        for client_id, websocket in list(self.clients.items()):
            # Skip the excluded client
            if exclude_client and client_id == exclude_client:
                continue

            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected_clients:
            await self.handle_client_disconnect(client_id)

    async def forward_with_broadcast(
        self, message: dict[str, Any], sender_id: str | None = None
    ) -> None:
        """
        Forward message to server and handle any necessary broadcasting

        Args:
            message: The message to forward
            sender_id: ID of the client sending the message
        """
        # Forward to server
        await self.forward_to_server(message, sender_id)

        # For transcription messages, broadcast to other clients
        if message.get("type") == "user-input-transcription":
            await self.broadcast_to_clients(message, exclude_client=sender_id)
