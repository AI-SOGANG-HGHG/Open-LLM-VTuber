"""Exercise the authenticated Studio/collector sockets with local model fixtures."""

import asyncio
from itertools import islice
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
from src.open_llm_vtuber.studio_audience import (
    QUESTIONS,
    AudienceQuestion,
    shuffled_topics,
)
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


class AudienceQuestionTests(unittest.TestCase):
    def test_votes_from_question_display_through_deadline(self):
        question = AudienceQuestion("late_snack")
        self.assertFalse(question.collect("1", 11.0))
        question.opened_at = 20.0
        self.assertFalse(question.collect("1", 19.99))
        self.assertTrue(question.collect("2번이요!", 20.0))
        self.assertTrue(question.collect("1번", 45.0))
        question.closes_at = 60.0
        self.assertFalse(question.collect("라면도 치킨도 좋아", 21.0))
        self.assertTrue(question.collect("라면!", 59.99))
        self.assertFalse(question.collect("1", 60.0))
        self.assertEqual(question.votes, [2, 1])

    def test_random_first_question_and_no_repeat_at_round_boundary(self):
        topics = list(QUESTIONS)
        with patch(
            "src.open_llm_vtuber.studio_audience.random.sample",
            side_effect=[topics[::-1], topics.copy(), topics.copy()],
        ):
            sequence = shuffled_topics()
            first = list(islice(sequence, len(topics)))
            second = list(islice(sequence, len(topics)))
            self.assertEqual(first[0], topics[-1])
            self.assertCountEqual(first, topics)
            self.assertCountEqual(second, topics)
            self.assertNotEqual(first[-1], second[0])
            self.assertEqual(next(shuffled_topics()), topics[0])


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

    async def test_collector_input_waits_for_profile_and_replays_through_studio(self):
        collector_headers = {"Authorization": f"Bearer {TOKEN}"}
        async with self.client.ws_connect(
            self.base + CHZZK_COLLECTOR_PATH, headers=collector_headers
        ) as collector:
            for text in ("발표가 잘 끝났어요!", "안녕!"):
                await collector.send_json(
                    {
                        "type": "text-input",
                        "source": "chzzk_chat",
                        "author": "시청자",
                        "text": text,
                    }
                )
            async with self.client.ws_connect(
                self.base + "/proxy-ws?mode=studio", headers=self.screen_headers()
            ) as screen:
                await self.select_agent(screen)
                selected = await self.receive(screen, "studio-persona-applied")
                self.assertEqual(selected["agent_id"], self.agent.agent_id)
                self.assertIsNone(self.llm.request)
                await screen.send_json({"type": "create-new-history"})
                await self.receive(screen, "new-history-created")
                await self.finish_spoken_turn(screen)  # Opening greeting
                for text in ("발표가 잘 끝났어요!", "안녕!"):
                    incoming = await self.receive(
                        screen, "user-input-transcription", text
                    )
                    request_id = incoming["request_id"]
                    started = await self.receive(
                        screen, "control", "conversation-chain-start"
                    )
                    self.assertEqual(started["request_id"], request_id)
                    trace = await self.receive(screen, "studio-turn-context")
                    self.assertEqual(trace["request_id"], request_id)
                    self.assertEqual(trace["expression"], "joy")
                    audio = await self.receive(screen, "audio")
                    self.assertEqual(audio["request_id"], request_id)
                    self.assertTrue(audio["audio"])
                    self.assertIn("방송 테스트 캐릭터", self.llm.generation_system)
                    if text.startswith("발표"):
                        self.assertIn("발표는 오전 열 시", str(self.llm.request))
                    await self.receive(screen, "backend-synth-complete")
                    await screen.send_json(
                        {"type": "frontend-playback-complete", "request_id": request_id}
                    )
                    completed = await self.receive(
                        screen, "control", "conversation-chain-end"
                    )
                    self.assertEqual(completed["request_id"], request_id)

    async def finish_spoken_turn(self, screen):
        started = await self.receive(screen, "control", "conversation-chain-start")
        request_id = started["request_id"]
        await self.receive(screen, "backend-synth-complete")
        await screen.send_json(
            {"type": "frontend-playback-complete", "request_id": request_id}
        )
        end = await self.receive(screen, "control", "conversation-chain-end")
        self.assertEqual(end["request_id"], request_id)

    async def test_audience_question_collects_votes_and_reacts_once(self):
        self.start_patch(
            patch("src.open_llm_vtuber.studio_broadcast.IDLE_SPEAK_SECONDS", 0.25)
        )
        self.start_patch(
            patch("src.open_llm_vtuber.studio_audience.ANSWER_SECONDS", 1.0)
        )
        async with (
            self.client.ws_connect(
                self.base + "/proxy-ws?mode=studio", headers=self.screen_headers()
            ) as screen,
            self.client.ws_connect(
                self.base + CHZZK_COLLECTOR_PATH,
                headers={"Authorization": f"Bearer {TOKEN}"},
            ) as collector,
        ):
            await self.select_agent(screen)
            await self.receive(screen, "studio-persona-applied")
            await screen.send_json({"type": "create-new-history"})
            await self.receive(screen, "new-history-created")
            await self.finish_spoken_turn(screen)
            # Even paraphrased speech has stable numbered choices on screen.
            started = await self.receive(screen, "control", "conversation-chain-start")
            question = started["audience_question"]
            first, second = question["choices"]
            await self.receive(screen, "backend-synth-complete")
            self.assertIn(question["text"], str(self.llm.request[-1]))
            await screen.send_json({"type": "text-input", "text": "1번"})
            self.assertEqual(
                (await self.receive(screen, "audience-vote-counts"))["votes"], [1, 0]
            )
            await asyncio.sleep(
                1.1
            )  # Playback still active beyond the usual answer interval
            await collector.send_json(
                {
                    "type": "text-input",
                    "source": "chzzk_chat",
                    "author": "시청자",
                    "text": second,
                }
            )
            self.assertEqual(
                (await self.receive(screen, "audience-vote-counts"))["votes"], [1, 1]
            )
            await screen.send_json(
                {
                    "type": "frontend-playback-complete",
                    "request_id": started["request_id"],
                }
            )
            await self.receive(screen, "control", "conversation-chain-end")
            self.llm.reply_chunks = ("맛있겠네!",)
            for text in (first, "다른 이야기"):
                await collector.send_json(
                    {
                        "type": "text-input",
                        "source": "chzzk_chat",
                        "author": "시청자",
                        "text": text,
                    }
                )
            incoming = await self.receive(screen, "user-input-transcription")
            self.assertEqual(incoming["text"], "다른 이야기")
            await self.finish_spoken_turn(screen)
            await self.finish_spoken_turn(screen)
            self.assertIn(f"{first} 2표, {second} 1표", str(self.llm.request[-1]))
            self.assertIn("방송 테스트 캐릭터", self.llm.generation_system)
            await self.finish_spoken_turn(screen)
            self.assertIn("채팅이 뜸해졌어", str(self.llm.request[-1]))
            await self.finish_spoken_turn(screen)
            self.assertNotIn(question["text"], str(self.llm.request[-1]))
            await self.finish_spoken_turn(screen)
            self.assertIn("채팅이 뜸해졌어", str(self.llm.request[-1]))

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
