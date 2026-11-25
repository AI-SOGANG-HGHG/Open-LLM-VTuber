"""Local asynchronous unit tests: no Minecraft or LLM required."""

import asyncio
import unittest

from starlette.websockets import WebSocketDisconnect
from src.open_llm_vtuber.game_ws_relay import GameWsRelay

TOKEN = "a-safe-test-secret-which-is-long-enough"


class FakeWebSocket:
    def __init__(self):
        self.inbox = asyncio.Queue()
        self.outbox = asyncio.Queue()
        self.closed_code = None

    async def accept(self):
        return None

    async def receive_json(self):
        message = await self.inbox.get()
        if message is None:
            raise WebSocketDisconnect(1000)
        return message

    async def send_json(self, msg):
        await self.outbox.put(msg)

    async def close(self, code=1000):
        self.closed_code = code

    async def receive(self, msg):
        await self.inbox.put(msg)

    async def sent(self):
        return await asyncio.wait_for(self.outbox.get(), timeout=1)


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.relay = GameWsRelay(token=TOKEN, timeout_seconds=0.3)
        self.tasks = []
        self.sockets = []

    async def asyncTearDown(self):
        for socket in self.sockets:
            await socket.receive(None)
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def connect(self, role, token=TOKEN):
        ws = FakeWebSocket()
        self.sockets.append(ws)
        await ws.receive({'type': 'game.register', 'role': role, 'token': token})
        task = asyncio.create_task(self.relay.handle_connection(ws))
        self.tasks.append(task)
        if token == TOKEN:
            result = await ws.sent()
            self.assertEqual(result['type'], 'game.registered')
        return ws

    async def test_round_trip_and_results_only_return_to_requester(self):
        mc = await self.connect('minecraft')
        controller = await self.connect('controller')
        unrelated = await self.connect('controller')
        await controller.receive({'type': 'game.command', 'id': 'c-123', 'action': 'get_self', 'params': {}})
        request = await mc.sent()
        self.assertEqual(request, {'type': 'game.command', 'id': 'c-123', 'action': 'get_self', 'params': {}})
        await mc.receive({'type': 'game.result', 'id': 'c-123', 'ok': True, 'data': {'health': 20}})
        self.assertEqual((await controller.sent())['data']['health'], 20)
        self.assertTrue(unrelated.outbox.empty())

    async def test_rejects_invalid_token(self):
        ws = await self.connect('minecraft', token='wrong')
        await asyncio.wait_for(self.tasks[-1], timeout=2)
        self.assertEqual(ws.closed_code, 1008)
        self.assertIsNone(self.relay.adapter)

    async def test_rejects_unsupported_commands(self):
        await self.connect('minecraft')
        controller = await self.connect('controller')
        await controller.receive({'type': 'game.command', 'id': 'c-5', 'action': 'run_command', 'params': {}})
        result = await controller.sent()
        self.assertEqual(result['error']['code'], 'ACTION_NOT_ALLOWED')

    async def test_move_disabled_by_default(self):
        mc = await self.connect('minecraft')
        controller = await self.connect('controller')
        await controller.receive({'type': 'game.command', 'id': 'c-5', 'action': 'move_to', 'params': {'x': 1, 'y': 70, 'z': 1}})
        self.assertEqual((await controller.sent())['error']['code'], 'MOVEMENT_DISABLED')
        self.assertTrue(mc.outbox.empty())

    async def test_timeout_result(self):
        await self.connect('minecraft')
        controller = await self.connect('controller')
        await controller.receive({'type': 'game.command', 'id': 'timeout-1', 'action': 'get_status'})
        result = await controller.sent()
        self.assertEqual(result['error']['code'], 'TIMEOUT')

    async def test_missing_adapter(self):
        controller = await self.connect('controller')
        await controller.receive({'type': 'game.command', 'id': 'missing-1', 'action': 'get_self'})
        result = await controller.sent()
        self.assertEqual(result['error']['code'], 'ADAPTER_OFFLINE')

    async def test_state_broadcast_only_to_authenticated_controller(self):
        mc = await self.connect('minecraft')
        controller = await self.connect('controller')
        await mc.receive({'type': 'game.state', 'data': {'health': 15}})
        self.assertEqual((await controller.sent())['data']['health'], 15)


class LiveWebSocketTransportTests(unittest.TestCase):
    """Proves that real FastAPI WebSocket message transport follows the relay."""

    def test_two_clients_exchange_command_result(self):
        from fastapi import FastAPI, WebSocket
        from fastapi.testclient import TestClient

        app = FastAPI()
        relay = GameWsRelay(token=TOKEN)

        @app.websocket("/proxy-ws")
        async def endpoint(websocket: WebSocket):
            await relay.handle_connection(websocket)

        with TestClient(app) as client:
            with client.websocket_connect("/proxy-ws?mode=game") as game_ws:
                game_ws.send_json({"type": "game.register", "role": "minecraft", "token": TOKEN})
                self.assertEqual(game_ws.receive_json()["type"], "game.registered")
                with client.websocket_connect("/proxy-ws?mode=game") as controller:
                    controller.send_json({"type": "game.register", "role": "controller", "token": TOKEN})
                    self.assertEqual(controller.receive_json()["type"], "game.registered")
                    controller.send_json({"type": "game.command", "id": "live-1", "action": "get_self", "params": {}})
                    self.assertEqual(game_ws.receive_json()["action"], "get_self")
                    game_ws.send_json({"type": "game.result", "id": "live-1", "ok": True, "data": {"health": 20}})
                    self.assertEqual(controller.receive_json()["data"]["health"], 20)

if __name__ == '__main__':
    unittest.main()
