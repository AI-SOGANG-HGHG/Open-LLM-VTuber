"""Exercise turn completion, instant acknowledgments and cancellation without API calls."""

import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from src.open_llm_vtuber.agent.output_types import DisplayText, SentenceOutput
from src.open_llm_vtuber.config_manager.utils import validate_config
from src.open_llm_vtuber.conversations.single_conversation import (
    process_single_conversation,
)
from src.open_llm_vtuber.conversations.tts_manager import TTSTaskManager
from src.open_llm_vtuber.message_handler import message_handler


class TextAgent:
    def __init__(self, texts=None):
        self.texts = texts or ("첫 번째 문장입니다.", "두 번째 문장입니다.")

    async def chat(self, batch):
        for text in self.texts:
            yield SentenceOutput(DisplayText(text), "", None)


class ConversationPlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def run_turn(self, streaming, history_uid=None, agent=None):
        with open(
            "config_templates/conf.gemini.example.yaml", encoding="utf-8"
        ) as source:
            config = validate_config(yaml.safe_load(source))
        context = SimpleNamespace(
            asr_engine=None,
            agent_engine=agent or TextAgent(),
            character_config=config.character_config,
            live2d_model=None,
            tts_engine=None,
            translate_engine=None,
            history_uid=history_uid,
        )
        messages = []
        client_uid = f"playback-test-{streaming}"

        async def send(payload):
            item = json.loads(payload)
            if item["type"] == "audio":
                await asyncio.sleep(0.005)
            messages.append(item)
            if item["type"] == "backend-synth-complete":
                message_handler.handle_message(
                    client_uid, {"type": "frontend-playback-complete"}
                )

        try:
            await asyncio.wait_for(
                process_single_conversation(
                    context,
                    send,
                    client_uid,
                    "테스트 입력",
                    metadata={"text_stream": True} if streaming else None,
                ),
                timeout=2,
            )
        finally:
            message_handler.cleanup_client(client_uid)
        return messages

    async def test_muted_client_can_ack_immediately_after_every_payload_arrives(self):
        messages = await self.run_turn(True)
        types = [item["type"] for item in messages]
        self.assertEqual(types.count("audio"), 2)
        self.assertEqual(types.count("backend-synth-complete"), 1)
        self.assertLess(
            max(i for i, t in enumerate(types) if t == "audio"),
            types.index("backend-synth-complete"),
        )
        self.assertEqual(types.count("text-response"), 2)
        self.assertLess(types.index("text-response"), types.index("audio"))
        self.assertEqual(
            messages[-1], {"type": "control", "text": "conversation-chain-end"}
        )

    async def test_legacy_client_does_not_receive_extra_text_messages(self):
        messages = await self.run_turn(False)
        self.assertFalse(any(item["type"] == "text-response" for item in messages))
        self.assertEqual(
            sum(item["type"] == "backend-synth-complete" for item in messages), 1
        )

    async def test_saved_streamed_reply_matches_visible_sentences_and_keeps_legacy_format(
        self,
    ):
        texts = ["[joy] 첫 문장.", " [neutral] 두 번째 문장. "]
        for streaming in [True, False]:
            with self.subTest(streaming=streaming):
                with patch(
                    "src.open_llm_vtuber.conversations.single_conversation.store_message"
                ) as store:
                    await self.run_turn(
                        streaming,
                        history_uid="synthetic-record",
                        agent=TextAgent(texts),
                    )
                replies = [
                    call.kwargs["content"]
                    for call in store.call_args_list
                    if call.kwargs.get("role") == "ai"
                ]
                self.assertEqual(
                    replies, ["첫 문장. 두 번째 문장." if streaming else "".join(texts)]
                )

    async def test_pcm_arrives_before_sentence_end_and_sentences_stay_in_order(self):
        release = asyncio.Event()
        first_audio = asyncio.Event()
        messages = []

        async def stream(text):
            yield text + "1"
            await release.wait()
            yield text + "2"

        async def send(payload):
            messages.append(json.loads(payload))
            first_audio.set()

        manager = TTSTaskManager(pcm_stream=stream)
        try:
            for text in ("첫", "다음"):
                await manager.speak(text, DisplayText(text), None, None, None, send)
            await asyncio.wait_for(first_audio.wait(), timeout=1)
            self.assertEqual([item["pcm"] for item in messages], ["첫1"])
            release.set()
            await asyncio.wait_for(manager.wait_for_completion(), timeout=1)
            self.assertEqual([item["pcm"] for item in messages], ["첫1", "첫2", "다음1", "다음2"])
            self.assertEqual([item["display_text"]["text"] for item in messages if "display_text" in item], ["첫", "다음"])
        finally:
            manager.clear()

    async def test_sender_failure_does_not_leave_completion_waiting_forever(self):
        manager = TTSTaskManager()

        async def disconnected(payload):
            raise ConnectionError("test socket is closed")

        try:
            await manager.speak("", DisplayText("test"), None, None, None, disconnected)
            with self.assertRaises(ConnectionError):
                await asyncio.wait_for(manager.wait_for_completion(), timeout=1)
        finally:
            manager.clear()

    async def test_interrupt_cancels_inflight_synthesis(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class BlockingTTS:
            async def async_generate_audio(self, **kwargs):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        manager = TTSTaskManager()

        async def send(payload):
            pass

        try:
            await manager.speak(
                "test", DisplayText("test"), None, None, BlockingTTS(), send
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            manager.clear()
            await asyncio.wait_for(cancelled.wait(), timeout=1)
        finally:
            manager.clear()
