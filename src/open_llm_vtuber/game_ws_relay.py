"""Authenticated game-message lane for the existing /proxy-ws endpoint.

The original dialogue WebSocket queue is intentionally untouched. Only
/proxy-ws?mode=game is routed here; default /proxy-ws remains unchanged.
"""

import asyncio
import hmac
import json
import os
import re
from typing import Any

from fastapi import WebSocket
from loguru import logger
from starlette.websockets import WebSocketDisconnect

READ_ACTIONS = frozenset({
    "get_status", "get_self", "get_inventory", "describe_scene",
    "navigation_status", "poll_events",
})
OTHER_ACTIONS = frozenset({"stop", "move_to"})
MAX_MESSAGE_SIZE = 16_384
ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


class GameWsRelay:
    """Routes game commands from authorized controllers to one game adapter."""

    def __init__(self, token: str | None = None, *, timeout_seconds: float = 35.0):
        self.token = token if token is not None else os.getenv("MINECRAFT_WS_TOKEN", "")
        self.allow_movement = os.getenv("MINECRAFT_WS_ALLOW_MOVEMENT", "false").lower() == "true"
        self.timeout_seconds = timeout_seconds
        self.adapter: WebSocket | None = None
        self.controllers: set[WebSocket] = set()
        # request ID -> (requester websocket, timeout task)
        self.pending: dict[str, tuple[WebSocket, asyncio.Task]] = {}

    @staticmethod
    async def _send(ws: WebSocket, message: dict[str, Any]):
        try:
            await ws.send_json(message)
        except (RuntimeError, WebSocketDisconnect, OSError):
            pass  # Peer disconnected; the connection handler will clean up.

    @staticmethod
    def _error(request_id: str | None, code: str, message: str) -> dict:
        return {
            "type": "game.result", "id": request_id, "ok": False,
            "error": {"code": code, "message": message},
        }

    async def handle_connection(self, websocket: WebSocket) -> None:
        await websocket.accept()
        role = None
        try:
            # Fail CLOSED unless an explicit shared token has been configured.
            if not self.token or len(self.token) < 20:
                logger.error("MINECRAFT_WS_TOKEN is missing or too short; game channel disabled")
                await websocket.close(code=1008)
                return
            hello = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            if not isinstance(hello, dict) or hello.get("type") != "game.register":
                await websocket.close(code=1008)
                return
            given_token = hello.get("token")
            if not isinstance(given_token, str) or not hmac.compare_digest(
                given_token, self.token
            ):
                await websocket.close(code=1008)
                return
            role = hello.get("role")
            if role == "minecraft":
                if self.adapter is not None:
                    await websocket.close(code=1008)
                    return
                self.adapter = websocket
            elif role == "controller":
                self.controllers.add(websocket)
            else:
                await websocket.close(code=1008)
                return
            await self._send(websocket, {"type": "game.registered", "role": role, "protocol": 1})
            logger.info("Game WebSocket {} connected", role)

            while True:
                data = await websocket.receive_json()
                if not isinstance(data, dict) or len(json.dumps(data)) > MAX_MESSAGE_SIZE:
                    await self._send(websocket, self._error(None, "INVALID_MESSAGE", "Invalid or oversized JSON"))
                    continue
                if role == "controller":
                    await self._controller_message(websocket, data)
                else:
                    await self._adapter_message(data)
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        except (json.JSONDecodeError, ValueError, RuntimeError) as error:
            logger.warning("Game WebSocket closed due to protocol error: %s", type(error).__name__)
        finally:
            if role == "minecraft" and self.adapter is websocket:
                self.adapter = None
                for request_id, (controller, timer) in list(self.pending.items()):
                    timer.cancel()
                    self.pending.pop(request_id, None)
                    await self._send(controller, self._error(request_id, "ADAPTER_OFFLINE", "Minecraft adapter disconnected"))
            if role == "controller":
                self.controllers.discard(websocket)
                for request_id, (controller, timer) in list(self.pending.items()):
                    if controller is websocket:
                        timer.cancel()
                        self.pending.pop(request_id, None)

    async def _controller_message(self, ws: WebSocket, data: dict) -> None:
        if data.get("type") != "game.command":
            await self._send(ws, self._error(None, "INVALID_TYPE", "Expected game.command"))
            return
        request_id = data.get("id")
        action = data.get("action")
        params = data.get("params", {})
        if not isinstance(request_id, str) or not ID_PATTERN.fullmatch(request_id):
            await self._send(ws, self._error(None, "INVALID_ID", "id must be 1-96 safe characters"))
            return
        if action not in READ_ACTIONS | OTHER_ACTIONS:
            await self._send(ws, self._error(request_id, "ACTION_NOT_ALLOWED", "Unsupported action"))
            return
        if action == "move_to" and not self.allow_movement:
            await self._send(ws, self._error(request_id, "MOVEMENT_DISABLED", "Set MINECRAFT_WS_ALLOW_MOVEMENT=true to enable movement"))
            return
        if not isinstance(params, dict):
            await self._send(ws, self._error(request_id, "INVALID_PARAMS", "params must be an object"))
            return
        if action == "move_to":
            if set(params) != {"x", "y", "z"} or any(
                not isinstance(params[k], int) or isinstance(params[k], bool)
                or abs(params[k]) > 30_000_000 for k in ("x", "y", "z")
            ):
                await self._send(ws, self._error(request_id, "INVALID_PARAMS", "move_to requires integer x, y, z"))
                return
        elif params:
            await self._send(ws, self._error(request_id, "INVALID_PARAMS", "This action takes no params"))
            return
        if request_id in self.pending:
            await self._send(ws, self._error(request_id, "DUPLICATE_ID", "Request id already in use"))
            return
        if len(self.pending) >= 16:
            await self._send(ws, self._error(request_id, "BUSY", "Too many requests"))
            return
        if self.adapter is None:
            await self._send(ws, self._error(request_id, "ADAPTER_OFFLINE", "Minecraft adapter not connected"))
            return
        timer = asyncio.create_task(self._expire_request(request_id))
        self.pending[request_id] = (ws, timer)
        try:
            await self.adapter.send_json({
                "type": "game.command", "id": request_id,
                "action": action, "params": params,
            })
        except (RuntimeError, WebSocketDisconnect, OSError):
            self.pending.pop(request_id, None)
            timer.cancel()
            await self._send(ws, self._error(request_id, "ADAPTER_OFFLINE", "Failed to forward command"))

    async def _adapter_message(self, data: dict) -> None:
        if data.get("type") in {"game.state", "game.event"}:
            # Game state goes only to authenticated controllers, never the chat queue.
            for controller in list(self.controllers):
                await self._send(controller, data)
            return
        if data.get("type") != "game.result":
            return
        request_id = data.get("id")
        pending = self.pending.pop(request_id, None) if isinstance(request_id, str) else None
        if pending is None:
            return  # Ignore unsolicited/stale results.
        controller, timer = pending
        timer.cancel()
        # No token or internal routing metadata in result packets.
        await self._send(controller, data)

    async def _expire_request(self, request_id: str) -> None:
        try:
            await asyncio.sleep(self.timeout_seconds)
            pending = self.pending.pop(request_id, None)
            if pending:
                await self._send(pending[0], self._error(request_id, "TIMEOUT", "Minecraft response timed out"))
        except asyncio.CancelledError:
            pass
