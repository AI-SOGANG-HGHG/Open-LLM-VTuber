"""Verify page login, private APIs, cookie sessions and live socket revocation."""

import argparse
import asyncio
import json
from pathlib import Path

from dotenv import dotenv_values
import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus


async def check(credentials_path):
    settings = dotenv_values(credentials_path, interpolate=False)
    origin = settings["PUBLIC_URL"].rstrip("/")
    if not origin.startswith("https://"):
        raise ValueError("PUBLIC_URL must use HTTPS")
    checks = []
    with httpx.Client(base_url=origin, timeout=15) as client:
        response = client.get("/web-tool/platform/")
        assert (
            response.status_code == 200 and "www-authenticate" not in response.headers
        )
        checks.append("Public login page: 200, no browser authentication challenge")
        image = client.get("/web-tool/sogangi/assets/sogangi-cheer.svg")
        assert image.status_code == 200, "Login page Sogangi illustration is unavailable"
        assert image.headers["content-type"].split(";", 1)[0] == "image/svg+xml"
        checks.append("Public login page Sogangi illustration: 200 SVG")
        assert client.get("/auth/session").json() == {
            "enabled": True,
            "authenticated": False,
            "username": None,
        }
        for path in (
            "/docs",
            "/web-tool/platform/runtime/",
            "/live2d-models/mao_pro/runtime/mao_pro.model3.json",
        ):
            assert client.get(path).status_code == 401, path
            checks.append(f"Unauthenticated {path}: 401")
        invalid = client.post(
            "/auth/login",
            headers={"Origin": origin},
            json={"username": settings["TEAM_USERNAME"], "password": "wrong-password"},
        )
        assert invalid.status_code == 401
        checks.append("Wrong password rejected")
        response = client.post(
            "/auth/login",
            headers={"Origin": origin},
            json={
                "username": settings["TEAM_USERNAME"],
                "password": settings["TEAM_PASSWORD"],
            },
        )
        assert response.status_code == 200
        for flag in ("Secure", "HttpOnly", "SameSite=strict", "Path=/"):
            assert flag in response.headers["set-cookie"]
        cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        assert client.get("/auth/session").json()["authenticated"]
        checks.append("Page login and cookie session restored")
        for path in (
            "/web-tool/platform/runtime/",
            "/web-tool/platform/js/main.js",
            "/live2d-models/mao_pro/runtime/mao_pro.model3.json",
        ):
            assert client.get(path).status_code == 200, path
            checks.append(f"Authenticated {path}: 200")
        uri = origin.replace("https://", "wss://", 1) + "/client-ws"
        for headers, allowed_origin in (
            ({}, origin),
            ({"Cookie": cookie}, "https://other.invalid"),
        ):
            try:
                async with connect(
                    uri,
                    origin=allowed_origin,
                    additional_headers=headers,
                    open_timeout=15,
                ):
                    raise AssertionError("Unauthorized socket accepted")
            except InvalidStatus as error:
                assert error.response.status_code == 403
        checks.append("Anonymous and cross-origin WebSockets rejected")
        async with connect(
            uri, origin=origin, additional_headers={"Cookie": cookie}, open_timeout=15
        ) as websocket:
            async with asyncio.timeout(20):
                while True:
                    item = json.loads(await websocket.recv())
                    if (
                        item.get("type") == "control"
                        and item.get("text") == "start-mic"
                    ):
                        break
            checks.append("Authenticated WebSocket initialized")
            assert (
                client.post("/auth/logout", headers={"Origin": origin}).status_code
                == 204
            )
            try:
                await asyncio.wait_for(websocket.recv(), timeout=5)
            except ConnectionClosed as error:
                assert error.code == 4401
            else:
                raise AssertionError("Logout did not close the socket")
        assert not client.get("/auth/session").json()["authenticated"]
        assert client.get("/docs", headers={"Cookie": cookie}).status_code == 401
        checks.append("Logout revoked the copied cookie and closed the active socket")
    print(
        json.dumps(
            {"checks": checks, "model_api_calls": 0}, ensure_ascii=False, indent=2
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials", type=Path, default=Path("private/web-access.env")
    )
    asyncio.run(check(parser.parse_args().credentials))


if __name__ == "__main__":
    main()
