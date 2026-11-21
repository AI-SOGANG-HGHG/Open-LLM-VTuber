import unittest
import yaml

from src.open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent
from src.open_llm_vtuber.config_manager.utils import validate_config
from src.open_llm_vtuber.conversations.conversation_utils import create_batch_input
from src.open_llm_vtuber.live2d_model import Live2dModel


class FakeLLM:
    def __init__(self, response):
        self.response = response

    async def chat_completion(self, *args, **kwargs):
        if self.response:
            yield self.response


class EmptyResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_studio_retries_silence_before_displaying_text(self):
        class SilentFirstLLM:
            def __init__(self):
                self.attempts = 0

            async def chat_completion(self, *args, **kwargs):
                self.attempts += 1
                yield "[neu"
                yield "tral] "
                yield "..." if self.attempts == 1 else "짧게 답하겠습니다."

        llm = SilentFirstLLM()
        with open(
            "config_templates/conf.gemini.example.yaml", encoding="utf-8"
        ) as file:
            preprocessor = validate_config(
                yaml.safe_load(file)
            ).character_config.tts_preprocessor_config
        agent = BasicMemoryAgent(llm, "test", Live2dModel("mao_pro"), preprocessor)
        batch = create_batch_input(input_text="test", images=None, from_name="test")
        batch.studio_context = "{}"
        outputs = [item async for item in agent.chat(batch)]
        self.assertEqual(llm.attempts, 2)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].display_text.text, "[neutral] 짧게 답하겠습니다.")

    async def test_studio_retries_an_upstream_failure_before_text(self):
        class TemporarilyUnavailable(RuntimeError):
            status_code = 503

        class FlakyLLM:
            def __init__(self):
                self.attempts = 0

            async def chat_completion(self, *args, **kwargs):
                self.attempts += 1
                if self.attempts == 1:
                    raise TemporarilyUnavailable
                yield "다시 연결됐어요."

        llm = FlakyLLM()
        with open(
            "config_templates/conf.gemini.example.yaml", encoding="utf-8"
        ) as file:
            preprocessor = validate_config(
                yaml.safe_load(file)
            ).character_config.tts_preprocessor_config
        agent = BasicMemoryAgent(llm, "test", Live2dModel("mao_pro"), preprocessor)
        batch = create_batch_input(input_text="test", images=None, from_name="test")
        batch.studio_context = "{}"
        outputs = [item async for item in agent.chat(batch)]
        self.assertEqual(llm.attempts, 2)
        self.assertEqual(outputs[0].display_text.text, "다시 연결됐어요.")

    async def test_empty_or_expression_only_response_cannot_be_saved_as_a_reply(self):
        with open(
            "config_templates/conf.gemini.example.yaml", encoding="utf-8"
        ) as source:
            preprocessor = validate_config(
                yaml.safe_load(source)
            ).character_config.tts_preprocessor_config
        for response in ("", "[neutral", "[neutral]", "[joy] [neutral]"):
            with self.subTest(response=response):
                agent = BasicMemoryAgent(
                    FakeLLM(response), "test", Live2dModel("mao_pro"), preprocessor
                )
                batch = create_batch_input(
                    input_text="test",
                    images=None,
                    from_name="test",
                    metadata={"require_spoken_response": True},
                )
                with self.assertRaisesRegex(ValueError, "no spoken text"):
                    async for output in agent.chat(batch):
                        pass
                self.assertFalse(
                    any(item["role"] == "assistant" for item in agent._memory)
                )

    async def test_legacy_expression_only_action_remains_supported(self):
        with open(
            "config_templates/conf.gemini.example.yaml", encoding="utf-8"
        ) as source:
            preprocessor = validate_config(
                yaml.safe_load(source)
            ).character_config.tts_preprocessor_config
        agent = BasicMemoryAgent(
            FakeLLM("[joy]"), "test", Live2dModel("mao_pro"), preprocessor
        )
        batch = create_batch_input(
            input_text="expression action", images=None, from_name="test"
        )
        outputs = [item async for item in agent.chat(batch)]
        self.assertTrue(outputs)
        self.assertEqual(agent._memory[-1]["content"], "[joy]")
