import json
import unittest
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI

from src.open_llm_vtuber.agent.stateless_llm_factory import LLMFactory


class LLMFailurePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def make_engine(self, transport, **options):
        def configured_client(**kwargs):
            return AsyncOpenAI(
                **kwargs, http_client=httpx.AsyncClient(transport=transport)
            )

        with patch(
            "src.open_llm_vtuber.agent.stateless_llm.openai_compatible_llm.AsyncOpenAI",
            side_effect=configured_client,
        ):
            return LLMFactory.create_llm(
                "gemini_llm",
                model="test-model",
                base_url="https://fixture.invalid/v1",
                llm_api_key="test-only-key",
                request_timeout=45,
                max_retries=0,
                **options,
            )

    async def test_opt_in_timeout_is_reported_as_failure_without_a_hidden_retry(self):
        requests = []

        def timeout(request):
            requests.append(request)
            raise httpx.ReadTimeout("fixture timeout", request=request)

        engine = await self.make_engine(
            httpx.MockTransport(timeout), raise_on_error=True
        )
        try:
            self.assertEqual(engine.client.timeout, 45)
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                async for item in engine.chat_completion(
                    [{"role": "user", "content": "test"}]
                ):
                    self.fail("A failed API request must not become a spoken reply")
            self.assertEqual(len(requests), 1)
        finally:
            await engine.client.close()

    async def test_opt_in_rate_limit_is_not_spoken_as_an_assistant_answer(self):
        def limited(request):
            return httpx.Response(
                429,
                request=request,
                json={"error": {"message": "fixture limit", "type": "rate_limit"}},
            )

        engine = await self.make_engine(
            httpx.MockTransport(limited), raise_on_error=True
        )
        try:
            with self.assertRaisesRegex(RuntimeError, "rate limit"):
                async for item in engine.chat_completion(
                    [{"role": "user", "content": "test"}]
                ):
                    self.fail("Rate limit errors are not successful answers")
        finally:
            await engine.client.close()

    async def test_normal_stream_still_returns_text(self):
        def response(request):
            chunks = []
            for delta, reason in [({"content": "test reply"}, None), ({}, "stop")]:
                chunks.append(
                    "data: "
                    + json.dumps(
                        {
                            "id": "fixture",
                            "object": "chat.completion.chunk",
                            "created": 1,
                            "model": "test-model",
                            "choices": [
                                {"index": 0, "delta": delta, "finish_reason": reason}
                            ],
                        }
                    )
                    + "\n\n"
                )
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "text/event-stream"},
                content="".join(chunks) + "data: [DONE]\n\n",
            )

        engine = await self.make_engine(
            httpx.MockTransport(response), raise_on_error=True
        )
        try:
            output = [
                item
                async for item in engine.chat_completion(
                    [{"role": "user", "content": "test"}]
                )
            ]
            self.assertEqual("".join(output), "test reply")
        finally:
            await engine.client.close()
