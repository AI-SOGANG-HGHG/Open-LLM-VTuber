import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from loguru import logger
from pydantic import ValidationError
import yaml

from src.open_llm_vtuber.config_manager.utils import validate_config
from src.open_llm_vtuber.service_context import ServiceContext
from src.open_llm_vtuber.studio_persona import StudioPersona, apply_studio_persona
from src.open_llm_vtuber.websocket_handler import WebSocketHandler


def payload(**updates):
    return dict(
        workspace_id=str(uuid4()),
        character_id="character-a",
        name="테스트 동료",
        description="계획을 돕는 동료",
        persona="작은 단계로 설명한다.",
        tone="차분한 존댓말",
        avatar="mao",
        exploration=35,
        memories=["회의의 암호는 민트별이다."],
        **updates,
    )


def context_fixture():
    with open("config_templates/conf.gemini.example.yaml", encoding="utf-8") as source:
        config = validate_config(yaml.safe_load(source))
    context = ServiceContext()
    context.config = config
    context.system_config = config.system_config
    context.character_config = config.character_config
    context.live2d_model = object()
    context.agent_engine = SimpleNamespace(close=AsyncMock())
    context.construct_system_prompt = AsyncMock(side_effect=lambda text: text)
    return context


class StudioPersonaTests(unittest.IsolatedAsyncioTestCase):
    def test_scope_is_stable_and_separates_workspace_and_character(self):
        first = StudioPersona(**payload())
        same = first.model_copy()
        other_character = first.model_copy(update={"character_id": "character-b"})
        other_workspace = first.model_copy(update={"workspace_id": uuid4()})
        self.assertEqual(first.history_scope, same.history_scope)
        self.assertNotEqual(first.history_scope, other_character.history_scope)
        self.assertNotEqual(first.history_scope, other_workspace.history_scope)

    def test_rejects_engine_overrides_paths_and_excessive_memory(self):
        examples = [
            {**payload(), "llm_configs": {"key": "untrusted"}},
            {**payload(), "character_id": "../../conf.yaml"},
            {**payload(), "memories": ["item"] * 51},
            {**payload(), "avatar": "https://external/model.json"},
        ]
        for example in examples:
            with (
                self.subTest(example=list(example)),
                self.assertRaises(ValidationError),
            ):
                StudioPersona(**example)

    async def test_apply_uses_server_engines_and_does_not_mutate_other_context(self):
        first, second = context_fixture(), context_fixture()
        original_config = first.config
        old_agent = first.agent_engine
        other_name = second.character_config.character_name
        new_agent = object()
        profile = StudioPersona(**payload())
        with patch(
            "src.open_llm_vtuber.studio_persona.AgentFactory.create_agent",
            return_value=new_agent,
        ) as factory:
            await apply_studio_persona(first, profile)
        self.assertEqual(first.character_config.character_name, profile.name)
        self.assertEqual(first.character_config.conf_uid, profile.history_scope)
        self.assertIn("민트별", factory.call_args.kwargs["system_prompt"])
        self.assertIn("차분한 존댓말", factory.call_args.kwargs["system_prompt"])
        self.assertTrue(
            factory.call_args.kwargs["llm_configs"]["gemini_llm"]["raise_on_error"]
        )
        self.assertFalse(
            original_config.character_config.agent_config.llm_configs.gemini_llm.raise_on_error
        )
        self.assertIs(first.agent_engine, new_agent)
        self.assertEqual(second.character_config.character_name, other_name)
        self.assertNotEqual(
            original_config.character_config.conf_uid, profile.history_scope
        )
        old_agent.close.assert_awaited_once()

    async def test_failed_initialization_leaves_previous_agent_and_history(self):
        context = context_fixture()
        context.history_uid = "previous-history"
        old_agent, old_config = context.agent_engine, context.character_config
        with patch(
            "src.open_llm_vtuber.studio_persona.AgentFactory.create_agent",
            side_effect=RuntimeError("fixture failure"),
        ):
            with self.assertRaises(RuntimeError):
                await apply_studio_persona(context, StudioPersona(**payload()))
        self.assertIs(context.agent_engine, old_agent)
        self.assertIs(context.character_config, old_config)
        self.assertEqual(context.history_uid, "previous-history")
        old_agent.close.assert_not_awaited()

    async def test_handler_rejects_profile_change_during_a_turn(self):
        handler = WebSocketHandler(ServiceContext())
        handler.current_conversation_tasks["client"] = SimpleNamespace(
            done=lambda: False
        )
        websocket = SimpleNamespace(send_text=AsyncMock())
        await handler._handle_studio_persona(
            websocket, "client", {"profile": payload()}
        )
        response = json.loads(websocket.send_text.call_args.args[0])
        self.assertEqual(response, {"type": "studio-persona-error", "code": "busy"})

    async def test_invalid_profile_returns_no_private_payload(self):
        handler = WebSocketHandler(ServiceContext())
        websocket = SimpleNamespace(send_text=AsyncMock())
        await handler._handle_studio_persona(
            websocket, "client", {"profile": {"api_key": "do-not-echo"}}
        )
        response = websocket.send_text.call_args.args[0]
        self.assertNotIn("do-not-echo", response)
        self.assertEqual(json.loads(response)["code"], "invalid_profile")


if __name__ == "__main__":
    logger.remove()
    unittest.main()
