"""Identify broadcast turns at the authenticated server-to-server boundary."""

from dataclasses import dataclass
from ipaddress import ip_address
import json
import os
from secrets import compare_digest

from fastapi import WebSocket


BROADCAST_TOKEN_HEADER = "x-studio-broadcast-token"


@dataclass(frozen=True)
class BroadcastTurn:
    """Link one response to its audience and original input event."""

    channel_id: str
    event_id: str
    request_id: str
    viewer_id: str | None
    room: bool

    @property
    def room_scope(self) -> str:
        """Return the public memory scope for this channel."""
        return json.dumps([self.channel_id, "room"], separators=(",", ":"))

    @property
    def scope(self) -> str:
        """Return the scope for the addressed viewer or public room."""
        if self.room:
            return self.room_scope
        kind, identity = (
            ("viewer", self.viewer_id) if self.viewer_id else ("event", self.event_id)
        )
        return json.dumps([self.channel_id, kind, identity], separators=(",", ":"))

    @property
    def scopes(self) -> tuple[str, ...]:
        """Return the memory scopes visible to the current turn."""
        return (self.scope,) if self.room else (self.scope, self.room_scope)

    @classmethod
    def from_socket(cls, socket: WebSocket, message: dict) -> "BroadcastTurn | None":
        """Accept identity only from the authenticated loopback broadcast bridge."""
        token = os.getenv("STUDIO_CHZZK_TOKEN", "")
        supplied = socket.headers.get(BROADCAST_TOKEN_HEADER, "")
        if (
            not token
            or not supplied
            or not compare_digest(token.encode(), supplied.encode())
        ):
            return None
        try:
            loopback = (
                socket.client is not None and ip_address(socket.client.host).is_loopback
            )
        except ValueError:
            loopback = False
        if not loopback:
            return None
        data = message.get("studio_broadcast")
        if not isinstance(data, dict):
            return None
        channel, event, request, viewer = (
            data.get("channel_id"),
            data.get("event_id"),
            message.get("request_id"),
            data.get("viewer_id"),
        )
        if not all(
            isinstance(value, str) and 0 < len(value) <= 128
            for value in (channel, event, request)
        ):
            return None
        viewer = (
            viewer
            if isinstance(viewer, str)
            and 0 < len(viewer) <= 128
            and viewer != "anonymous"
            else None
        )
        return cls(channel, event, request, viewer, data.get("room") is True)
