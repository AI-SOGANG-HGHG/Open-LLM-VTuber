"""Conversation state belongs to a connection, while speech engines may be shared."""

import unittest
from unittest.mock import patch

from loguru import logger
import yaml

from src.open_llm_vtuber.config_manager.utils import validate_config
from src.open_llm_vtuber.live2d_model import Live2dModel
from src.open_llm_vtuber.service_context import ServiceContext
from src.open_llm_vtuber.websocket_handler import WebSocketHandler


class MemoryAgent:
    def __init__(self):
        self.memory = []

    def remember(self, value):
        self.memory.append(value)

    def set_memory_from_history(self, *args, **kwargs):
        self.memory.clear()


class SessionIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_connection_cannot_change_another_connections_memory(self):
        with open(
            "config_templates/conf.gemini.example.yaml", encoding="utf-8"
        ) as source:
            config = validate_config(yaml.safe_load(source))
        default = ServiceContext()
        default.config = config
        default.system_config = config.system_config
        default.character_config = config.character_config
        default.live2d_model = Live2dModel(config.character_config.live2d_model_name)
        default.asr_engine = object()
        default.tts_engine = object()
        default.agent_engine = MemoryAgent()
        handler = WebSocketHandler(default)

        async def send_text(payload):
            pass

        with patch(
            "src.open_llm_vtuber.service_context.AgentFactory.create_agent",
            side_effect=lambda **kwargs: MemoryAgent(),
        ):
            first = await handler._init_service_context(send_text, "isolation-first")
            second = await handler._init_service_context(send_text, "isolation-second")

        first.agent_engine.remember("test-first-only")
        self.assertEqual(second.agent_engine.memory, [])
        second.agent_engine.remember("test-second-only")
        first.agent_engine.set_memory_from_history("test", "history")
        self.assertEqual(second.agent_engine.memory, ["test-second-only"])
        self.assertEqual(default.agent_engine.memory, [])
        self.assertIs(first.asr_engine, second.asr_engine)
        self.assertIs(first.tts_engine, second.tts_engine)


if __name__ == "__main__":
    logger.remove()
    unittest.main()
