"""Authentication is enforced by the server for HTTP, cookies, and live sockets."""

import base64
import os
import unittest
from unittest.mock import patch

import bcrypt
from fastapi import FastAPI, WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.open_llm_vtuber.studio_auth import (
    COOKIE,
    LOGIN_PAGE,
    StudioAuth,
    install_studio_auth,
)

ORIGIN = "https://studio.test"
PASSWORD = "synthetic-test-password"


class StudioAuthTests(unittest.TestCase):
    def setUp(self):
        password_hash = bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt(rounds=4)
        ).decode()
        self.auth = StudioAuth("team", password_hash, ORIGIN)
        self.app = FastAPI()

        @self.app.get(LOGIN_PAGE)
        async def landing():
            return {"screen": "login"}

        @self.app.api_route("/private", methods=["GET", "POST"])
        async def private():
            return {"private": True}

        @self.app.websocket("/client-ws")
        async def socket(websocket: WebSocket):
            await websocket.accept()
            await websocket.send_text("ready")
            try:
                while True:
                    await websocket.receive_text()
                    await websocket.send_text("received")
            except WebSocketDisconnect:
                pass

        install_studio_auth(self.app, self.auth)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def login(self, **updates):
        return self.client.post(
            "/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "team", "password": PASSWORD, **updates},
        )

    def test_public_login_and_session_have_no_browser_auth_challenge(self):
        self.assertEqual(self.client.get(LOGIN_PAGE).status_code, 200)
        status = self.client.get("/auth/session")
        self.assertFalse(status.json()["authenticated"])
        denied = self.client.get("/private")
        self.assertEqual(denied.status_code, 401)
        self.assertNotIn("www-authenticate", denied.headers)
        redirected = self.client.get(
            "/private", headers={"Accept": "text/html"}, follow_redirects=False
        )
        self.assertEqual(redirected.headers["location"], LOGIN_PAGE)

    def test_correct_login_sets_private_secure_cookie_and_refresh_restores_session(
        self,
    ):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"]
        for attribute in (
            "HttpOnly",
            "Secure",
            "SameSite=strict",
            "Path=/",
            "Max-Age=28800",
        ):
            self.assertIn(attribute, cookie)
        self.assertNotIn("Domain=", cookie)
        self.assertNotIn(self.client.cookies.get(COOKIE), response.text)
        self.assertEqual(self.client.get("/private").status_code, 200)
        self.assertEqual(self.client.get("/auth/session").json()["username"], "team")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_bad_credentials_do_not_echo_password_or_create_a_session(self):
        for fields in (
            {"password": "wrong"},
            {"username": "other"},
            {"password": "x" * 73},
        ):
            response = self.login(**fields)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"error": "invalid_credentials"})
            self.assertNotIn("set-cookie", response.headers)

    def test_forged_cookie_and_cached_basic_credentials_cannot_bypass_login(self):
        basic = base64.b64encode(f"team:{PASSWORD}".encode()).decode()
        denied = self.client.get(
            "/private",
            headers={
                "Cookie": f"{COOKIE}={'x' * 43}",
                "Authorization": "Basic " + basic,
            },
        )
        self.assertEqual(denied.status_code, 401)

    def test_cross_origin_login_mutations_and_logout_are_rejected(self):
        response = self.client.post(
            "/auth/login",
            headers={"Origin": "https://other.test"},
            json={"username": "team", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 403)
        self.login()
        self.assertEqual(self.client.post("/private").status_code, 403)
        for path in ("/private", "/auth/session"):
            self.assertEqual(
                self.client.get(
                    path, headers={"Origin": "https://other.test"}
                ).status_code,
                403,
            )
        self.assertEqual(
            self.client.post("/private", headers={"Origin": ORIGIN}).status_code, 200
        )
        self.assertEqual(
            self.client.post(
                "/auth/logout", headers={"Origin": "https://other.test"}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/private").status_code, 200)

    def test_malformed_and_oversized_login_requests_are_bounded(self):
        headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
        self.assertEqual(
            self.client.post("/auth/login", headers=headers, content="[]").status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/auth/login", headers=headers, content="x" * 8193
            ).status_code,
            413,
        )
        self.assertEqual(
            self.client.post(
                "/auth/login", headers={"Origin": ORIGIN}, data={"username": "team"}
            ).status_code,
            400,
        )

    def test_attempts_are_rate_limited(self):
        self.auth.limit = 2
        self.assertEqual(self.login(password="wrong").status_code, 401)
        self.assertEqual(self.login(password="wrong").status_code, 401)
        response = self.login()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")

    def test_logout_revokes_a_copied_cookie_and_closes_an_existing_socket(self):
        self.login()
        copied = self.client.cookies.get(COOKIE)
        with self.client.websocket_connect(
            "wss://studio.test/client-ws", headers={"Origin": ORIGIN}
        ) as socket:
            self.assertEqual(socket.receive_text(), "ready")
            response = self.client.post("/auth/logout", headers={"Origin": ORIGIN})
            self.assertEqual(response.status_code, 204)
            self.assertIn("Max-Age=0", response.headers["set-cookie"])
            self.assertEqual(socket.receive()["code"], 4401)
        self.assertEqual(
            self.client.get(
                "/private", headers={"Cookie": f"{COOKIE}={copied}"}
            ).status_code,
            401,
        )

    def test_expired_sessions_are_denied(self):
        self.login()
        current = self.auth.now()
        self.auth.now = lambda: current + self.auth.ttl + 1
        self.assertEqual(self.client.get("/private").status_code, 401)
        self.assertFalse(self.client.get("/auth/session").json()["authenticated"])

    def test_sockets_require_both_a_session_and_the_allowed_origin(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                "wss://studio.test/client-ws", headers={"Origin": ORIGIN}
            ):
                self.fail("Anonymous socket accepted")
        self.login()
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(
                "wss://studio.test/client-ws", headers={"Origin": "https://other.test"}
            ):
                self.fail("Cross-origin socket accepted")

    def test_required_auth_fails_closed_when_configuration_is_missing(self):
        with patch.dict(os.environ, {"STUDIO_AUTH_REQUIRED": "true"}, clear=True):
            with self.assertRaises(ValueError):
                StudioAuth.from_environment()


if __name__ == "__main__":
    unittest.main()
