"""Exercise the authenticated Studio/collector sockets with local model fixtures."""

import asyncio
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4
import wave

import aiohttp
import bcrypt
from fastapi import FastAPI
import uvicorn

from src.open_llm_vtuber.routes import init_client_ws_route, init_proxy_route
from src.open_llm_vtuber.studio_auth import (
    CHZZK_COLLECTOR_PATH,
    COOKIE,
    StudioAuth,
    install_studio_auth,
)
from src.open_llm_vtuber.studio_persona import StudioPersona
from src.open_llm_vtuber.studio_registry import StudioRegistry, WORKSPACE_COOKIE
from test_studio_persona import RecordedStudioLLM, context_fixture, payload


ORIGIN = "https://studio.test"
TOKEN = "local-test-collector-token"


class StudioBroadcastTests(unittest.IsolatedAsyncioTestCase):
    def start_patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncSetUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        registry = StudioRegistry(directory / "studio.sqlite3")
        data = payload(preset_id="warm")
        data.update(
            name="방송 테스트 캐릭터", memories=["발표는 오전 열 시에 시작한다."]
        )
        self.workspace = data["workspace_id"]
        self.workspace_cookie = registry.register_workspace(self.workspace, "")
        self.agent = registry.create(
            StudioPersona.model_validate(data), self.workspace_cookie
        )
        self.other_workspace_cookie = registry.register_workspace(str(uuid4()), "")
        context = context_fixture()
        context.character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp = False
        self.llm = RecordedStudioLLM()
        self.llm.expression_hint = "joy"
        wav = directory / "sample.wav"
        with wave.open(str(wav), "wb") as output:
            output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            output.writeframes(b"\x00\x08" * 1600)
        context.tts_engine = Mock(async_generate_audio=AsyncMock(return_value=str(wav)))
        self.start_patch(
            patch(
                "src.open_llm_vtuber.chat_history_manager._conf_directory",
                side_effect=lambda uid: directory / uid,
            )
        )
        self.start_patch(
            patch(
                "src.open_llm_vtuber.agent.agent_factory.StatelessLLMFactory.create_llm",
                return_value=self.llm,
            )
        )
        self.start_patch(
            patch(
                "src.open_llm_vtuber.live.ai_chat_classifier._load_llm_credentials_from_conf",
                return_value=("", "", ""),
            )
        )

        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        upstream = f"ws://127.0.0.1:{port}/client-ws"
        app = FastAPI()
        password = bcrypt.hashpw(b"test-password", bcrypt.gensalt(rounds=4)).decode()
        install_studio_auth(app, StudioAuth("team", password, ORIGIN))
        app.include_router(init_client_ws_route(context, registry))
        with patch.dict("os.environ", {"STUDIO_CHZZK_TOKEN": TOKEN}):
            app.include_router(init_proxy_route(upstream, upstream))

        server = uvicorn.Server(
            uvicorn.Config(app, log_level="critical", lifespan="off")
        )
        task = asyncio.create_task(server.serve(sockets=[listener]))

        async def stop_server():
            server.should_exit = True
            await asyncio.wait_for(task, timeout=5)

        self.addAsyncCleanup(stop_server)
        for _ in range(150):
            if server.started:
                break
            await asyncio.sleep(0.01)
        self.assertTrue(server.started)
        self.client = aiohttp.ClientSession()
        self.addAsyncCleanup(self.client.close)
        async with self.client.post(
            self.base + "/auth/login",
            headers={"Origin": ORIGIN},
            json={"username": "team", "password": "test-password"},
        ) as response:
            self.assertEqual(response.status, 200)
            self.session_cookie = response.cookies[COOKIE].value

    def screen_headers(self, workspace=None):
        return {
            "Origin": ORIGIN,
            "Cookie": f"{COOKIE}={self.session_cookie}; {WORKSPACE_COOKIE}={workspace or self.workspace_cookie}",
        }

    async def receive(self, ws, kind, text=None):
        return await asyncio.wait_for(self._receive(ws, kind, text), timeout=5)

    async def _receive(self, ws, kind, text):
        while True:
            event = await ws.receive()
            self.assertEqual(event.type, aiohttp.WSMsgType.TEXT, event)
            data = event.json()
            self.assertNotEqual(data.get("type"), "chzzk-chat-board")
            if kind == "control" and text == "conversation-chain-start":
                self.assertNotEqual(data.get("type"), "user-input-transcription")
            if data.get("type") == kind and (text is None or data.get("text") == text):
                return data

    async def select_agent(self, screen):
        await self.receive(screen, "set-model-and-conf")
        await screen.send_json(
            {
                "type": "apply-studio-persona",
                "workspace_id": self.workspace,
                "agent_id": self.agent.agent_id,
            }
        )

    async def send_chat(self, collector, text, author="시청자", *, donation=None):
        await collector.send_json(
            {
                "type": "text-input",
                "source": "chzzk_chat" if donation is None else "chzzk_donation",
                "author": author,
                "text": text,
                "amount": donation,
            }
        )

    async def receive_turn(self, screen, expected_text, *, candidates=None):
        if expected_text is not None:
            incoming = await self.receive(
                screen, "user-input-transcription", expected_text
            )
            self.assertEqual(set(incoming), {"type", "text", "request_id"})
        started = await self.receive(screen, "control", "conversation-chain-start")
        request_id = started["request_id"]
        if expected_text is not None:
            self.assertEqual(incoming["request_id"], request_id)
        trace = await self.receive(screen, "studio-turn-context")
        self.assertEqual(trace["request_id"], request_id)
        audio = await self.receive(screen, "audio")
        self.assertEqual(audio["request_id"], request_id)
        self.assertTrue(audio["audio"])
        self.assertIn("방송 테스트 캐릭터", self.llm.generation_system)
        if candidates is not None:
            model_input = self.llm.request[-1]["content"][-1]["text"]
            self.assertEqual(json.loads(model_input), candidates)
            self.assertIn("비슷한 질문은 하나로 묶고", self.llm.generation_system)
        await self.receive(screen, "backend-synth-complete")
        return request_id

    async def receive_chat(self, screen, text):
        self.assertEqual(
            await self.receive(screen, "chzzk-chat", text),
            {"type": "chzzk-chat", "text": text},
        )

    async def finish_playback(self, screen, request_id):
        await screen.send_json(
            {"type": "frontend-playback-complete", "request_id": request_id}
        )
        completed = await self.receive(screen, "control", "conversation-chain-end")
        self.assertEqual(completed["request_id"], request_id)

    async def test_collector_input_waits_for_profile_and_batches_during_playback(self):
        async with (
            self.client.ws_connect(
                self.base + CHZZK_COLLECTOR_PATH,
                headers={"Authorization": f"Bearer {TOKEN}"},
            ) as collector,
            self.client.ws_connect(
                self.base + "/proxy-ws?mode=studio", headers=self.screen_headers()
            ) as screen,
        ):
            await self.send_chat(collector, "발표는 몇 시에 시작해요?")
            await self.select_agent(screen)
            selected = await self.receive(screen, "studio-persona-applied")
            self.assertEqual(selected["agent_id"], self.agent.agent_id)
            self.assertIsNone(self.llm.request)
            await screen.send_json({"type": "create-new-history"})
            await self.receive(screen, "new-history-created")
            await self.receive_chat(screen, "발표는 몇 시에 시작해요?")
            first = await self.receive_turn(
                screen,
                None,
                candidates=[{"author": "시청자", "text": "발표는 몇 시에 시작해요?"}],
            )
            self.assertIn("발표는 오전 열 시", str(self.llm.request))
            await self.send_chat(collector, "안녕!")
            await self.receive_chat(screen, "안녕!")

            questions = [
                "오늘 어떤 게임 해?",
                "마인크래프트 할 거야?",
                "방송 몇 시까지 해?",
                "마크 언제 시작해?",
                "발표는 어떤 주제인가요?",
            ]
            previous_generation = self.llm.request
            for index, question in enumerate(questions):
                await self.send_chat(collector, question, f"시청자{index}")
                await self.receive_chat(screen, question)
            await self.send_chat(collector, "🎮")
            await self.receive_chat(screen, "🎮")
            await self.send_chat(collector, "방송 응원합니다", donation=1000)
            await self.send_chat(collector, "마크  언제 시작해?", "새시청자")
            await self.receive_chat(screen, "마크  언제 시작해?")

            self.assertIs(previous_generation, self.llm.request)
            await self.finish_playback(screen, first)

            donation = await self.receive_turn(screen, "방송 응원합니다")
            self.assertIsNot(previous_generation, self.llm.request)
            await self.finish_playback(screen, donation)

            candidates = [
                {"author": "시청자4", "text": questions[4]},
                {"author": "시청자2", "text": questions[2]},
                {"author": "새시청자", "text": "마크  언제 시작해?"},
                {"author": "시청자1", "text": questions[1]},
                {"author": "시청자0", "text": questions[0]},
            ]
            batch = await self.receive_turn(screen, None, candidates=candidates)
            await self.finish_playback(screen, batch)

    async def test_expired_chat_stays_visible_but_is_excluded_from_the_next_turn(self):
        async with (
            self.client.ws_connect(
                self.base + CHZZK_COLLECTOR_PATH,
                headers={"Authorization": f"Bearer {TOKEN}"},
            ) as collector,
            self.client.ws_connect(
                self.base + "/proxy-ws?mode=studio", headers=self.screen_headers()
            ) as screen,
        ):
            await self.select_agent(screen)
            await self.receive(screen, "studio-persona-applied")
            await screen.send_json({"type": "create-new-history"})
            await self.receive(screen, "new-history-created")
            await screen.send_json({"type": "text-input", "text": "방송 시작합니다"})
            current = await self.receive_turn(screen, "방송 시작합니다")
            with patch("src.open_llm_vtuber.studio_chat_board.CANDIDATE_TTL", 0.25):
                await self.send_chat(collector, "오래된 질문이에요?")
                await self.receive_chat(screen, "오래된 질문이에요?")
                await asyncio.sleep(0.3)
                await self.send_chat(collector, "새 질문이에요?")
                await self.receive_chat(screen, "새 질문이에요?")
                await self.finish_playback(screen, current)
                fresh = await self.receive_turn(
                    screen,
                    None,
                    candidates=[{"author": "시청자", "text": "새 질문이에요?"}],
                )
            await self.finish_playback(screen, fresh)

    async def test_browser_and_collector_credentials_are_checked_independently(self):
        screen_url = self.base + "/proxy-ws?mode=studio"
        for url, headers in (
            (screen_url, {"Origin": ORIGIN}),
            (screen_url, {**self.screen_headers(), "Origin": "https://elsewhere.test"}),
            (self.base + CHZZK_COLLECTOR_PATH, {"Authorization": "Bearer incorrect"}),
        ):
            with self.assertRaises(aiohttp.WSServerHandshakeError):
                await self.client.ws_connect(url, headers=headers)
        async with self.client.ws_connect(
            screen_url, headers=self.screen_headers(self.other_workspace_cookie)
        ) as screen:
            await self.select_agent(screen)
            rejected = await self.receive(screen, "studio-persona-error")
            self.assertEqual(rejected["code"], "invalid_profile")
            async with self.client.post(
                self.base + "/auth/logout", headers=self.screen_headers()
            ) as response:
                self.assertEqual(response.status, 204)
            self.assertIsNone(self.llm.request)
            while (await screen.receive(timeout=5)).type == aiohttp.WSMsgType.TEXT:
                pass
            self.assertTrue(screen.closed)
