"""Shared team login with server-owned, revocable HTTP and WebSocket sessions."""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit

import bcrypt
from fastapi import APIRouter, Request
from starlette.datastructures import Headers
from starlette.requests import cookie_parser
from starlette.responses import JSONResponse, RedirectResponse, Response

COOKIE = "__Host-studio_session"
LOGIN_PAGE = "/web-tool/platform/"
PUBLIC_PATHS = frozenset(
    {
        LOGIN_PAGE,
        LOGIN_PAGE + "index.html",
        LOGIN_PAGE + "js/auth.js",
        LOGIN_PAGE + "js/components/avatar-preview.js",
        LOGIN_PAGE + "js/components/card.js",
        LOGIN_PAGE + "js/dom.js",
        LOGIN_PAGE + "js/main.js",
        LOGIN_PAGE + "js/presets.js",
        LOGIN_PAGE + "js/router.js",
        LOGIN_PAGE + "js/runtime-bridge.js",
        LOGIN_PAGE + "js/state.js",
        LOGIN_PAGE + "js/store.js",
        LOGIN_PAGE + "js/views/character-detail.js",
        LOGIN_PAGE + "js/views/characters.js",
        LOGIN_PAGE + "js/views/connections.js",
        LOGIN_PAGE + "js/views/create-form.js",
        LOGIN_PAGE + "js/views/discover.js",
        LOGIN_PAGE + "js/views/records.js",
        LOGIN_PAGE + "style.css",
        LOGIN_PAGE + "assets/mark.svg",
        LOGIN_PAGE + "assets/mao.png",
        "/web-tool/sogangi/assets/sogangi-cheer.svg",
        "/web-tool/sogangi/assets/sogangi-neutral.svg",
    }
)


@dataclass
class Session:
    username: str
    expires: float
    revoked: asyncio.Event = field(default_factory=asyncio.Event)


class StudioAuth:
    def __init__(self, username, password_hash, origin, *, ttl=8 * 60 * 60, limit=10):
        address = urlsplit(origin)
        if (
            address.scheme != "https"
            or not address.hostname
            or address.path not in ("", "/")
            or address.query
            or address.fragment
            or address.username
            or address.password
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username)
        ):
            raise ValueError("Invalid Studio authentication configuration")
        try:
            bcrypt.checkpw(b"", password_hash.encode())
        except (ValueError, TypeError):
            raise ValueError("Invalid Studio password hash") from None
        self.username = username
        self.password_hash = password_hash.encode()
        self.origin = origin.rstrip("/")
        self.ttl = ttl
        self.now = time.monotonic
        self.limit = limit
        self.sessions = {}
        self.attempts = {}
        self.all_attempts = deque()
        self.verifications = asyncio.Semaphore(2)

    @classmethod
    def from_environment(cls):
        enabled = os.environ.get("STUDIO_AUTH_ENABLED", "").lower() == "true"
        if not enabled:
            if os.environ.get("STUDIO_AUTH_REQUIRED", "").lower() == "true":
                raise ValueError("Studio authentication is required but not configured")
            return None
        return cls(
            os.environ.get("STUDIO_AUTH_USERNAME", ""),
            os.environ.get("STUDIO_AUTH_PASSWORD_HASH", ""),
            os.environ.get("STUDIO_PUBLIC_ORIGIN", ""),
        )

    def same_origin(self, headers):
        return headers.get("origin") == self.origin

    def resolve(self, headers):
        for digest, session in list(self.sessions.items()):
            if session.expires <= self.now():
                session.revoked.set()
                self.sessions.pop(digest, None)
        token = cookie_parser(headers.get("cookie", "")).get(COOKIE, "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            return None
        return self.sessions.get(sha256(token.encode()).hexdigest())

    def revoke(self, headers):
        token = cookie_parser(headers.get("cookie", "")).get(COOKIE, "")
        session = self.sessions.pop(sha256(token.encode()).hexdigest(), None)
        if session:
            session.revoked.set()

    def allow_attempt(self, client):
        now = self.now()
        self.attempts = {
            key: deque(stamp for stamp in stamps if stamp > now - 60)
            for key, stamps in self.attempts.items()
            if stamps and stamps[-1] > now - 60
        }
        while self.all_attempts and self.all_attempts[0] <= now - 60:
            self.all_attempts.popleft()
        if len(self.attempts) >= 4096 and client not in self.attempts:
            return False
        attempts = self.attempts.setdefault(client, deque())
        if len(attempts) >= self.limit or len(self.all_attempts) >= 60:
            return False
        attempts.append(now)
        self.all_attempts.append(now)
        return True

    def router(self):
        router = APIRouter()

        @router.get("/auth/session")
        async def status(request: Request):
            session = self.resolve(request.headers)
            return JSONResponse(
                {
                    "enabled": True,
                    "authenticated": bool(session),
                    "username": session.username if session else None,
                },
                headers={"Cache-Control": "no-store"},
            )

        @router.post("/auth/login")
        async def login(request: Request):
            if not self.same_origin(request.headers):
                return JSONResponse({"error": "invalid_origin"}, status_code=403)
            client = request.client.host if request.client else "unknown"
            if not self.allow_attempt(client):
                return JSONResponse(
                    {"error": "too_many_attempts"},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            if (
                request.headers.get("content-type", "").split(";")[0]
                != "application/json"
            ):
                return JSONResponse({"error": "invalid_request"}, status_code=400)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 8192:
                    return JSONResponse({"error": "invalid_request"}, status_code=413)
            try:
                payload = json.loads(body)
                username, password = payload["username"], payload["password"]
                if not isinstance(username, str) or not isinstance(password, str):
                    raise ValueError()
                encoded = password.encode()
                if len(username) > 64 or not 1 <= len(encoded) <= 72:
                    return JSONResponse(
                        {"error": "invalid_credentials"}, status_code=401
                    )
            except (ValueError, TypeError, KeyError):
                return JSONResponse({"error": "invalid_request"}, status_code=400)
            async with self.verifications:
                valid = await asyncio.to_thread(
                    bcrypt.checkpw, encoded, self.password_hash
                )
            if not valid or not hmac.compare_digest(
                username.encode(), self.username.encode()
            ):
                return JSONResponse({"error": "invalid_credentials"}, status_code=401)
            self.resolve(request.headers)
            self.revoke(request.headers)
            if len(self.sessions) >= 128:
                oldest = min(
                    self.sessions, key=lambda digest: self.sessions[digest].expires
                )
                self.sessions.pop(oldest).revoked.set()
            token = secrets.token_urlsafe(32)
            self.sessions[sha256(token.encode()).hexdigest()] = Session(
                self.username, self.now() + self.ttl
            )
            response = JSONResponse({"username": self.username})
            response.set_cookie(
                COOKIE,
                token,
                max_age=int(self.ttl),
                secure=True,
                httponly=True,
                samesite="strict",
                path="/",
            )
            return response

        @router.post("/auth/logout")
        async def logout(request: Request):
            if not self.same_origin(request.headers):
                return JSONResponse({"error": "invalid_origin"}, status_code=403)
            self.revoke(request.headers)
            response = Response(status_code=204)
            response.delete_cookie(
                COOKIE, path="/", secure=True, httponly=True, samesite="strict"
            )
            return response

        return router


class StudioAuthMiddleware:
    def __init__(self, app, auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        session = self.auth.resolve(headers)
        if scope["type"] == "http":
            if headers.get("origin") and not self.auth.same_origin(headers):
                return await JSONResponse({"error": "invalid_origin"}, status_code=403)(
                    scope, receive, send
                )
            public = (
                scope["method"] in ("GET", "HEAD") and scope["path"] in PUBLIC_PATHS
            )
            public = public or scope["path"] in (
                "/auth/session",
                "/auth/login",
                "/auth/logout",
            )
            if not public and not session:
                response = (
                    RedirectResponse(LOGIN_PAGE, status_code=303)
                    if scope["method"] == "GET"
                    and "text/html" in headers.get("accept", "")
                    else JSONResponse(
                        {"error": "authentication_required"}, status_code=401
                    )
                )
                return await response(scope, receive, send)
            if scope["method"] not in (
                "GET",
                "HEAD",
                "OPTIONS",
            ) and not self.auth.same_origin(headers):
                return await JSONResponse({"error": "invalid_origin"}, status_code=403)(
                    scope, receive, send
                )

            async def private_send(message):
                if message["type"] == "http.response.start":
                    message["headers"] = [
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() != b"cache-control"
                    ] + [(b"cache-control", b"no-store")]
                await send(message)

            return await self.app(scope, receive, private_send)

        if not session or not self.auth.same_origin(headers):
            return await send({"type": "websocket.close", "code": 4401})
        closed = False

        async def guarded_send(message):
            nonlocal closed
            if message["type"] == "websocket.close":
                closed = True
            await send(message)

        async def guarded_receive():
            nonlocal closed
            incoming = asyncio.create_task(receive())
            revoked = asyncio.create_task(session.revoked.wait())
            try:
                done, _ = await asyncio.wait(
                    (incoming, revoked),
                    timeout=max(0, session.expires - self.auth.now()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if (
                    not session.revoked.is_set()
                    and session.expires > self.auth.now()
                    and incoming in done
                ):
                    return incoming.result()
                if not closed:
                    closed = True
                    await send({"type": "websocket.close", "code": 4401})
                return {"type": "websocket.disconnect", "code": 4401}
            finally:
                for task in (incoming, revoked):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(incoming, revoked, return_exceptions=True)

        await self.app(scope, guarded_receive, guarded_send)


def install_studio_auth(app, auth=None):
    auth = auth or StudioAuth.from_environment()
    if auth:
        app.include_router(auth.router())
        app.add_middleware(StudioAuthMiddleware, auth=auth)
    else:

        @app.get("/auth/session")
        async def preview_status():
            return {"enabled": False, "authenticated": False}

    return auth
