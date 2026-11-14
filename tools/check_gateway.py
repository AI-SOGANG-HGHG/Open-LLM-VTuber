"""Check HTTPS, team authentication, and WebSocket routing without model calls."""

import argparse
import asyncio
import base64
from http.client import HTTPSConnection
import json
from pathlib import Path
import socket
import ssl
from urllib.parse import urlsplit

from dotenv import dotenv_values
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus


class GatewayConnection(HTTPSConnection):
    def __init__(self, hostname, port, context, connect_host):
        super().__init__(hostname, port, context=context, timeout=15)
        self.connect_host = connect_host or hostname

    def connect(self):
        connection = socket.create_connection(
            (self.connect_host, self.port), self.timeout
        )
        self.sock = self._context.wrap_socket(connection, server_hostname=self.host)


async def check(args):
    settings = dotenv_values(args.credentials, interpolate=False)
    address = urlsplit(settings["PUBLIC_URL"])
    if address.scheme != "https" or not address.hostname:
        raise ValueError("PUBLIC_URL must be an HTTPS URL")
    hostname = address.hostname
    port = args.port or address.port or 443
    context = ssl.create_default_context(cafile=args.ca_file)
    credentials = f"{settings['TEAM_USERNAME']}:{settings['TEAM_PASSWORD']}".encode()
    authorization = "Basic " + base64.b64encode(credentials).decode()

    def request(path, authentication=None):
        headers = {"Host": f"{hostname}:{port}"}
        if authentication:
            headers["Authorization"] = authentication
        connection = GatewayConnection(hostname, port, context, args.connect_host)
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            response.read()
            return response.status, response.getheader("Location")
        finally:
            connection.close()

    checks = []
    for path in ("/", "/web-tool/platform/", "/docs", "/client-ws"):
        status, _ = request(path)
        assert status == 401, f"Unauthenticated {path}: expected 401, got {status}"
        checks.append(f"Unauthenticated {path}: 401")
    status, _ = request(
        "/web-tool/platform/",
        "Basic " + base64.b64encode(b"team:wrong-password").decode(),
    )
    assert status == 401, "Wrong password was accepted"
    checks.append("Wrong password: 401")
    status, location = request("/", authorization)
    assert status == 302 and location == "/web-tool/platform/"
    checks.append("Authenticated entry: redirects to Studio")
    for path in (
        "/web-tool/platform/",
        "/web-tool/platform/runtime/",
        "/web-tool/platform/app.js",
        "/live2d-models/mao_pro/runtime/mao_pro.model3.json",
    ):
        status, _ = request(path, authorization)
        assert status == 200, f"Authenticated {path}: expected 200, got {status}"
        checks.append(f"Authenticated {path}: 200")

    uri = f"wss://{hostname}:{port}/client-ws"
    options = {"ssl": context, "open_timeout": 15}
    if args.connect_host:
        options.update(host=args.connect_host, port=port, server_hostname=hostname)
    try:
        async with connect(uri, **options):
            raise AssertionError("Anonymous WebSocket was accepted")
    except InvalidStatus as error:
        assert error.response.status_code == 401
    checks.append("Unauthenticated WebSocket: 401")
    async with connect(
        uri, additional_headers={"Authorization": authorization}, **options
    ) as websocket:
        async with asyncio.timeout(20):
            while True:
                item = json.loads(await websocket.recv())
                if item.get("type") == "control" and item.get("text") == "start-mic":
                    break
    checks.append("Authenticated WebSocket: connected and initialized")
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
    parser.add_argument(
        "--connect-host", help="Override TCP destination for local checks"
    )
    parser.add_argument("--port", type=int, help="Override HTTPS port for local checks")
    parser.add_argument("--ca-file", help="Trust a specific CA file for local checks")
    asyncio.run(check(parser.parse_args()))


if __name__ == "__main__":
    main()
