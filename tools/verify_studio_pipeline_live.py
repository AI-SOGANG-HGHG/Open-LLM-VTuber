"""Run a small authenticated Studio broadcast test with synthetic OpenAI inputs."""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import getpass
import io
import json
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

from loguru import logger
from pydantic import ValidationError


def run(model: str, api_key: str) -> bool:
    """Use the Studio sockets with fixture audio and real model requests."""

    ROOT = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

    from src.open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM
    from src.open_llm_vtuber.studio_auth import CHZZK_COLLECTOR_PATH
    from src.open_llm_vtuber.studio_broadcast_context import BroadcastTurn
    from src.open_llm_vtuber.studio_profiles import studio_behavior_rules
    from src.open_llm_vtuber.studio_turn import Appraisal
    from test_studio_broadcast import TOKEN, StudioBroadcastTests

    class TracedOpenAI(AsyncLLM):
        """Record synthetic model inputs needed for assertions."""

        @staticmethod
        def failure(error: Exception) -> str:
            """Report provider status without credentials, request bodies or error messages."""
            cause = error.__cause__
            detail = str(cause).lower() if cause else ""
            safe_detail = next(
                (
                    item
                    for item in (
                        "certificate",
                        "getaddrinfo",
                        "proxy",
                        "permission",
                        "illegal header",
                        "closed",
                        "connect",
                    )
                    if item in detail
                ),
                "unspecified",
            )
            return (
                f"{type(error).__name__} status={getattr(error, 'status_code', None)} "
                f"code={getattr(error, 'code', None)} cause={type(cause).__name__} {safe_detail}"
            )

        async def embed_texts(self, model: str, texts: list[str]) -> list[list[float]]:
            try:
                return await super().embed_texts(model, texts)
            except Exception as error:
                self.embedding_failure = self.failure(error)
                raise

        async def chat_completion(self, messages, system=None, tools=None):
            appraisal = system and system.startswith("Evaluate the fictional character")
            generation = not system or not system.startswith(
                (
                    "Evaluate the fictional character",
                    "Select applicable",
                    "Treat both messages",
                )
            )
            if appraisal:
                self.appraisal_request = json.loads(messages[0]["content"])
            if generation:
                self.generation_request = messages
            try:
                pieces = []
                async for part in super().chat_completion(messages, system):
                    if (appraisal or generation) and isinstance(part, str):
                        pieces.append(part)
                    yield part
                if generation:
                    self.generation_reply = "".join(pieces)
                if appraisal:
                    data = "".join(pieces).strip()
                    data = (
                        data.removeprefix("```json")
                        .removeprefix("```")
                        .removesuffix("```")
                        .strip()
                    )
                    try:
                        Appraisal.model_validate_json(data)
                    except ValidationError as error:
                        self.appraisal_failure = [
                            (failure["loc"], failure["type"])
                            for failure in error.errors(include_input=False)
                        ]
            except Exception as error:
                self.chat_failure = self.failure(error)
                raise

    class LiveStudioBroadcast(StudioBroadcastTests):
        def create_model(self, *args, **kwargs):
            self.llm = self.model_fixture()
            return self.llm

        def model_fixture(self):
            provider = TracedOpenAI(
                model,
                "https://api.openai.com/v1",
                llm_api_key=api_key,
                organization_id=None,
                project_id=None,
                temperature=0,
                request_timeout=20,
                max_retries=0,
                raise_on_error=True,
            )
            self.addAsyncCleanup(provider.close)
            return provider

        async def receive(self, ws, kind, text=None):
            return await asyncio.wait_for(self._receive(ws, kind, text), timeout=30)

        async def test_live_pipeline(self):
            self.start_patch(
                patch("src.open_llm_vtuber.studio_turn.random", return_value=0)
            )
            now = datetime.now(timezone.utc)
            room_scope = BroadcastTurn(
                "synthetic-test-channel", "seed", "seed", None, True
            ).scope
            for event, days_ago, valence in (
                ("첫 공연", 1095, 0.98),
                ("블록 경주", 1, 0.75),
            ):
                event_time = now - timedelta(days=days_ago)
                self.registry.save_memory(
                    self.agent.agent_id,
                    {
                        "id": event,
                        "text": f"캐릭터는 {event}에서 성공하고 기뻐했다.",
                        "occurred_at": now.isoformat(),
                        "embedding_model": "",
                        "vector": None,
                        "broadcast_scope": room_scope,
                        "meaning": {
                            "kind": "experience",
                            "experiencer": "character",
                            "event_date": event_time.date().isoformat(),
                        },
                        "event_affect": {
                            "valence": valence,
                            "arousal": 0.8,
                            "dominance": 0.8,
                        },
                    },
                    (),
                )
            rule = next(
                item
                for item in studio_behavior_rules()
                if item.trait == "agreeableness"
                and item.direction == "high"
                and "가족" in item.situation
                and item.behavior
            )
            situations = (
                ("viewer-a", "제가 지은 자작나무 집을 다음에 같이 봐주세요."),
                ("viewer-b", "저는 보라색 보트를 만들었어요."),
                ("viewer-a", "그거 뭐였지?"),
                ("viewer-a", f"네가 이런 상황이면 어떻게 반응할래? {rule.situation}"),
                ("viewer-a", "최근에 가장 기뻤던 일이 뭐야?"),
                ("viewer-a", "인생에서 가장 기뻤던 일이 뭐야?"),
            )
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
                for viewer, text in situations:
                    await collector.send_json(
                        {
                            "type": "text-input",
                            "source": "chzzk_chat",
                            "channel_id": "synthetic-test-channel",
                            "user_id": viewer,
                            "author": "합성 시청자",
                            "text": text,
                        }
                    )
                    incoming = await self.receive(
                        screen, "user-input-transcription", text
                    )
                    trace = await self.receive(screen, "studio-turn-context")
                    self.assertEqual(
                        trace["retrieval"],
                        "ok",
                        getattr(self.llm, "embedding_failure", "embedding unavailable"),
                    )
                    self.assertEqual(
                        trace["appraisal"],
                        "ok",
                        getattr(
                            self.llm,
                            "chat_failure",
                            getattr(
                                self.llm, "appraisal_failure", "appraisal unavailable"
                            ),
                        ),
                    )
                    self.assertEqual(trace["request_id"], incoming["request_id"])
                    audio = await self.receive(screen, "audio")
                    self.assertTrue(audio["audio"])
                    if text.startswith("그거"):
                        for request in (
                            self.llm.appraisal_request,
                            self.llm.generation_request,
                        ):
                            self.assertIn("자작나무 집", str(request))
                            self.assertNotIn("보라색 보트", str(request))
                    if text.startswith("네가"):
                        self.assertEqual(trace["rule_selection"], "ok")
                        self.assertTrue(trace["rule_candidate_ids"])
                        self.assertTrue(trace["rules"])
                        self.assertTrue(
                            all(item["evidence"] in text for item in trace["rules"])
                        )
                    await self.receive(screen, "backend-synth-complete")
                    if text.startswith(("최근에", "인생에서")):
                        expected = (
                            "블록 경주" if text.startswith("최근에") else "첫 공연"
                        )
                        self.assertIn(expected, trace["memories"][0]["text"])
                        self.assertIn(expected, self.llm.generation_reply)
                    await screen.send_json(
                        {
                            "type": "frontend-playback-complete",
                            "request_id": incoming["request_id"],
                        }
                    )
                    await self.receive(screen, "control", "conversation-chain-end")

    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.TestSuite((LiveStudioBroadcast("test_live_pipeline"),))
    )
    print(re.sub(r"sk-[A-Za-z0-9_*-]+", "[redacted]", output.getvalue()), end="")
    return result.wasSuccessful()


if __name__ == "__main__":
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--model", default="gpt-4o-mini")
    arguments.add_argument(
        "--live", action="store_true", help="Enable paid model calls"
    )
    args = arguments.parse_args()
    if not args.live:
        arguments.error("pass --live to run the six synthetic turns")
    logger.remove()
    key = os.getenv("OPENAI_API_KEY") or getpass.getpass(
        "OpenAI integration test key: "
    )
    if not key:
        raise SystemExit("OpenAI API key unavailable")
    # The normal Studio profile binding chooses the encoder by provider.
    os.environ["STUDIO_EMBEDDING_MODEL"] = "text-embedding-3-small"
    raise SystemExit(not run(args.model, key))
