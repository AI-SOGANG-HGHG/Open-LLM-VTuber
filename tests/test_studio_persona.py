import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from loguru import logger
from pydantic import ValidationError
import yaml

from src.open_llm_vtuber.config_manager.utils import validate_config
from src.open_llm_vtuber.agent.agents.basic_memory_agent import BasicMemoryAgent
from src.open_llm_vtuber.agent.stateless_llm.openai_compatible_llm import AsyncLLM
from src.open_llm_vtuber.chat_history_manager import (
    create_new_history,
    delete_history,
    get_history,
    get_metadata,
)
from src.open_llm_vtuber.conversations.single_conversation import (
    process_single_conversation,
)
from src.open_llm_vtuber.message_handler import message_handler
from src.open_llm_vtuber.service_context import ServiceContext
from src.open_llm_vtuber.studio_persona import StudioPersona, apply_studio_persona
from src.open_llm_vtuber.studio_tasks import TASK_METADATA
from src.open_llm_vtuber.studio_turn import RECALL_METADATA, studio_presets
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
    def test_comparison_presets_share_context_and_differ_in_behavior(self):
        reviewer = studio_presets()["direct-reviewer"]
        coach = studio_presets()["supportive-coach"]
        self.assertEqual(reviewer.role, coach.role)
        self.assertEqual(reviewer.style, coach.style)
        self.assertEqual(reviewer.traits["curiosity"], coach.traits["curiosity"])
        self.assertGreater(
            reviewer.traits["assertiveness"], coach.traits["assertiveness"]
        )
        self.assertLess(reviewer.traits["warmth"], coach.traits["warmth"])
        self.assertEqual(
            [(rule.id, rule.situation) for rule in reviewer.rules],
            [(rule.id, rule.situation) for rule in coach.rules],
        )
        for review_rule, coach_rule in zip(reviewer.rules, coach.rules):
            self.assertNotEqual(review_rule.behavior, coach_rule.behavior)

    async def test_preset_profile_loads_server_configuration_without_a_prompt(self):
        request = payload()
        request.pop("persona")
        request.pop("tone")
        request["preset_id"] = "calm"
        profile = StudioPersona(**request)
        with self.assertRaises(ValidationError):
            StudioPersona(**{**request, "preset_id": "unknown"})
        context = context_fixture()
        agent = SimpleNamespace(enable_studio_runtime=Mock())
        with patch(
            "src.open_llm_vtuber.studio_persona.AgentFactory.create_agent",
            return_value=agent,
        ) as factory:
            await apply_studio_persona(context, profile)
        system_prompt = factory.call_args.kwargs["system_prompt"]
        self.assertIn("약속 준수", system_prompt)
        self.assertNotIn("민트별", system_prompt)
        self.assertEqual(
            agent.enable_studio_runtime.call_args.args[:2],
            ("calm", studio_presets()["calm"]),
        )

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


class StudioEmbeddingAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_may_omit_zero_index_for_single_and_batch_embeddings(self):
        create = AsyncMock(
            side_effect=[
                SimpleNamespace(data=[SimpleNamespace(embedding=[1.0])]),
                SimpleNamespace(
                    data=[
                        SimpleNamespace(index=1, embedding=[2.0]),
                        SimpleNamespace(index=None, embedding=[1.0]),
                    ]
                ),
                SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[1.0])]),
            ]
        )
        llm = SimpleNamespace(
            client=SimpleNamespace(embeddings=SimpleNamespace(create=create))
        )
        self.assertEqual(await AsyncLLM.embed_texts(llm, "fixture", ["하나"]), [[1.0]])
        self.assertEqual(
            await AsyncLLM.embed_texts(llm, "fixture", ["하나", "둘"]), [[1.0], [2.0]]
        )
        with self.assertRaises(ValueError):
            await AsyncLLM.embed_texts(llm, "fixture", ["하나", "둘"])


class RecordedStudioLLM:
    def __init__(self):
        self.request = None
        self.appraisal_request = None
        self.embedding_calls = []
        self.fail_embedding = False
        self.invalid_appraisal = False
        self.task_update = None

    async def embed_texts(self, model, texts):
        self.embedding_calls.append((model, texts))
        if self.fail_embedding:
            raise TimeoutError
        return [
            [1, 0, 0]
            if "음료" in text or "보리차" in text
            else [0, 1, 0]
            if "약속" in text
            else [0, 0, 1]
            for text in texts
        ]

    async def chat_completion(self, messages, system):
        if system.startswith("Evaluate the fictional character"):
            if self.invalid_appraisal:
                yield '{"affect": {"valence": 10}, "remember": false}'
                return
            self.appraisal_request = json.loads(messages[0]["content"])
            text = self.appraisal_request["input"]
            neutral_preference = "카페인" in text and "보리차" in text
            deadline_disclosure = "내일이 발표인데" in text
            yield json.dumps(
                {
                    "applicable_rule_ids": ["missed-promise"]
                    if "지난 번 약속" in text
                    else [],
                    "relevant_memory_ids": [
                        memory["id"]
                        for memory in self.appraisal_request["memory_candidates"]
                        if ("음료" in text and "보리차" in memory["text"])
                        or ("발표" in text and "발표" in memory["text"])
                    ],
                    "affect": None
                    if neutral_preference
                    else {"valence": 0.5, "arousal": 0.5, "dominance": 0.75},
                    "remember": deadline_disclosure
                    or neutral_preference
                    or "기억해 줘" in text,
                    "relevant_task_ids": [
                        task["id"]
                        for task in self.appraisal_request["stored_tasks"]
                        if "발표" in text
                    ],
                    "task_update": self.task_update,
                }
            )
            return
        self.request = messages
        yield "확인했습니다."


class StudioTurnTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = context_fixture()
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        history_root = patch(
            "src.open_llm_vtuber.chat_history_manager._conf_directory",
            side_effect=lambda conf_uid: Path(directory.name) / conf_uid,
        )
        history_root.start()
        self.addCleanup(history_root.stop)
        self.scope = self.context.character_config.conf_uid
        self.context.history_uid = create_new_history(self.scope)
        self.context.live2d_model = SimpleNamespace(
            extract_emotion=lambda text: [], remove_emotion_str=lambda text: text
        )
        self.connect_agent()

    def connect_agent(self, preset_id="calm"):
        preset = studio_presets()[preset_id]
        self.llm = RecordedStudioLLM()
        self.agent = BasicMemoryAgent(
            llm=self.llm,
            system=preset.system_prompt("서강이"),
            live2d_model=self.context.live2d_model,
            tts_preprocessor_config=self.context.character_config.tts_preprocessor_config,
            segment_method="regex",
        )
        self.agent.enable_studio_runtime(
            preset_id, preset, ("캠퍼스 셔틀은 네 시에 출발한다.",), "fixture"
        )
        self.context.agent_engine = self.agent

    async def turn(self, question):
        events = []
        client = "studio-turn-fixture"

        async def send(payload):
            event = json.loads(payload)
            events.append(event)
            if event["type"] == "backend-synth-complete":
                message_handler.handle_message(
                    client, {"type": "frontend-playback-complete"}
                )

        try:
            await process_single_conversation(
                self.context, send, client, question, metadata={"text_stream": True}
            )
        finally:
            message_handler.cleanup_client(client)
        return events

    async def test_old_user_fact_is_recalled_and_vad_carries_between_turns(self):
        original = "내가 좋아하는 음료는 보리차야. 기억해 줘."
        first = await self.turn(original)
        first_trace = next(e for e in first if e["type"] == "studio-turn-context")
        for index in range(14):
            self.agent._add_message(f"간단한 대화 {index}", "user")
        events = await self.turn("내가 어떤 음료를 좋아하지?")
        trace = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertEqual(trace["previous_affect"], first_trace["affect"])
        self.assertAlmostEqual(trace["affect"]["valence"], 0.32)
        self.assertEqual([memory["text"] for memory in trace["memories"]], [original])
        self.assertEqual(trace["memories"][0]["source"], "user_turn")
        self.assertTrue(trace["memories"][0]["occurred_at"])
        self.assertLess(
            events.index(trace),
            next(i for i, e in enumerate(events) if e["type"] == "text-response"),
        )
        context = self.llm.request[-1]["content"][0]["text"].split("\n", 1)[1]
        self.assertEqual(json.loads(context)["experience"], trace["memories"])
        self.assertNotIn(original, str(self.llm.request[:-1]))
        self.assertEqual(len(self.llm.embedding_calls[1][1]), 1)

        self.context.history_uid = create_new_history(self.scope)
        other = await self.turn("내가 어떤 음료를 좋아하지?")
        other_trace = next(e for e in other if e["type"] == "studio-turn-context")
        self.assertEqual(other_trace["memories"], [])
        self.assertEqual(other_trace["previous_affect"]["valence"], 0)

    async def test_selected_memory_survives_reconnection_and_follows_history_deletion(
        self,
    ):
        history_uid = self.context.history_uid
        original = "내가 좋아하는 음료는 보리차야. 기억해 줘."
        await self.turn(original)
        await self.turn(original)
        metadata = get_metadata(self.scope, history_uid)
        self.assertEqual([row["text"] for row in metadata[RECALL_METADATA]], [original])
        self.assertTrue(metadata[RECALL_METADATA][0]["vector"])
        self.assertNotIn(RECALL_METADATA, str(get_history(self.scope, history_uid)))

        self.connect_agent()
        self.agent.set_memory_from_history(self.scope, history_uid)
        events = await self.turn("내가 어떤 음료를 좋아하지?")
        trace = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertEqual(trace["previous_affect"]["valence"], 0)
        self.assertEqual([row["text"] for row in trace["memories"]], [original])

        self.assertTrue(delete_history(self.scope, history_uid))
        self.assertEqual(get_metadata(self.scope, history_uid), {})
        after = await self.agent.studio_runtime.prepare(
            self.scope, history_uid, "어떤 음료를 좋아하지?"
        )
        self.assertEqual(after.trace["memories"], [])

    async def test_rules_rank_separately_and_provider_failures_allow_a_reply(self):
        events = await self.turn("지난 번 약속을 지켜 줘.")
        valid = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertIn("missed-promise", [rule["id"] for rule in valid["rules"]])
        self.assertEqual(valid["memories"], [])
        self.llm.fail_embedding = True
        self.llm.invalid_appraisal = True
        events = await self.turn("다시 이야기하자.")
        trace = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertEqual(trace["retrieval"], "unavailable")
        self.assertEqual(trace["appraisal"], "unavailable")
        self.assertEqual(trace["affect"], valid["affect"])
        self.assertTrue(any(e["type"] == "text-response" for e in events))

    async def test_neutral_preference_keeps_affect_and_rejects_similar_rules(self):
        self.connect_agent("supportive-coach")
        text = "카페인에 민감해서 보리차만 마셔요."
        preset = studio_presets()["supportive-coach"]
        with patch.object(
            self.llm,
            "embed_texts",
            return_value=[[1, 0, 0]] * (len(preset.rules) + 2),
        ):
            events = await self.turn(text)

        self.assertEqual(len(self.llm.appraisal_request["rule_candidates"]), 2)
        trace = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertEqual(trace["appraisal"], "ok")
        self.assertEqual(trace["affect"], trace["previous_affect"])
        self.assertEqual(trace["rules"], [])
        context = self.llm.request[-1]["content"][0]["text"].split("\n", 1)[1]
        self.assertEqual(json.loads(context)["behavior_rules"], [])
        metadata = get_metadata(self.scope, self.context.history_uid)
        self.assertEqual([entry["text"] for entry in metadata[RECALL_METADATA]], [text])

    async def test_unrelated_memory_is_excluded_even_when_its_vector_matches(self):
        original = "내가 좋아하는 음료는 보리차야. 기억해 줘."
        await self.turn(original)
        with patch.object(self.llm, "embed_texts", return_value=[[1, 0, 0]]):
            events = await self.turn("발표는 지금 어때 상태야?")

        candidates = self.llm.appraisal_request["memory_candidates"]
        self.assertEqual([item["text"] for item in candidates], [original])
        trace = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertEqual(trace["retrieval"], "ok")
        self.assertEqual(trace["memories"], [])
        context = self.llm.request[-1]["content"][0]["text"].split("\n", 1)[1]
        self.assertEqual(json.loads(context)["experience"], [])

    async def test_deadline_and_drink_preference_are_saved_as_separate_memories(self):
        self.connect_agent("direct-reviewer")
        deadline = "내일이 발표인데 아직 초안도 작성하지 못했어."
        preference = "나는 카페인을 먹지 못해서 보리차만 마셔"
        await self.turn(deadline)
        await self.turn(preference)
        history_uid = self.context.history_uid
        metadata = get_metadata(self.scope, history_uid)
        self.assertEqual(
            [entry["text"] for entry in metadata[RECALL_METADATA]],
            [deadline, preference],
        )

        self.connect_agent("direct-reviewer")
        self.agent.set_memory_from_history(self.scope, history_uid)
        for question, expected in (
            ("내 발표는 언제라고 했지?", deadline),
            ("내가 어떤 음료를 마신다고 했지?", preference),
        ):
            events = await self.turn(question)
            trace = next(e for e in events if e["type"] == "studio-turn-context")
            self.assertEqual([item["text"] for item in trace["memories"]], [expected])

    async def test_interruption_preserves_event_affect_without_indexing_the_turn(self):
        with (
            patch(
                "src.open_llm_vtuber.conversations.single_conversation.finalize_conversation_turn",
                side_effect=asyncio.CancelledError,
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            await self.turn("좋아하는 음료는 보리차야. 기억해 줘.")
        events = await self.turn("어떤 음료를 좋아하지?")
        trace = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertEqual(trace["memories"], [])
        self.assertEqual(trace["previous_affect"]["valence"], 0.2)

    async def test_latest_task_state_survives_reconnection_after_memory_search_fails(
        self,
    ):
        history_uid = self.context.history_uid
        first = "내일이 발표인데 아직 초안도 작성하지 못했어."
        self.llm.task_update = {
            "task_id": None,
            "title": "발표 준비",
            "status": "in_progress",
            "evidence": first,
        }
        await self.turn(first)
        metadata = get_metadata(self.scope, history_uid)
        (original,) = metadata[TASK_METADATA]
        self.assertEqual(original["status"], "in_progress")
        self.assertEqual(
            original["source_event_id"], metadata[RECALL_METADATA][0]["id"]
        )

        finished = "발표 준비를 모두 끝냈어."
        self.llm.fail_embedding = True
        self.llm.task_update = {
            "task_id": original["id"],
            "title": "발표 준비",
            "status": "completed",
            "evidence": finished,
        }
        await self.turn(finished)
        (completed,) = get_metadata(self.scope, history_uid)[TASK_METADATA]
        self.assertEqual(completed["id"], original["id"])
        self.assertEqual(completed["status"], "completed")
        self.assertNotEqual(completed["source_event_id"], original["source_event_id"])
        self.assertIn(
            first, [row["content"] for row in get_history(self.scope, history_uid)]
        )

        self.connect_agent()
        self.agent.set_memory_from_history(self.scope, history_uid)
        for index in range(14):
            self.agent._add_message(f"다른 대화 {index}", "user")
        events = await self.turn("발표 준비 상태가 어떻게 돼?")
        trace = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertEqual(trace["task_states"], [completed])
        context = self.llm.request[-1]["content"][0]["text"].split("\n", 1)[1]
        self.assertEqual(json.loads(context)["task_states"], [completed])
        self.assertNotIn(finished, str(self.llm.request[:-1]))

        self.context.history_uid = create_new_history(self.scope)
        other = await self.turn("발표 준비 상태가 어떻게 돼?")
        trace = next(event for event in other if event["type"] == "studio-turn-context")
        self.assertEqual(trace["task_states"], [])

    async def test_task_update_needs_verbatim_evidence_and_a_completed_turn(self):
        history_uid = self.context.history_uid
        progress = "발표 준비를 시작했어."
        self.llm.task_update = {
            "task_id": None,
            "title": "발표 준비",
            "status": "completed",
            "evidence": "발표 준비가 끝났어.",
        }
        await self.turn(progress)
        self.assertNotIn(TASK_METADATA, get_metadata(self.scope, history_uid))

        self.llm.task_update.update(status="in_progress", evidence=progress)
        with (
            patch(
                "src.open_llm_vtuber.conversations.single_conversation.finalize_conversation_turn",
                side_effect=asyncio.CancelledError,
            ),
            self.assertRaises(asyncio.CancelledError),
        ):
            await self.turn(progress)
        self.assertNotIn(TASK_METADATA, get_metadata(self.scope, history_uid))


if __name__ == "__main__":
    logger.remove()
    unittest.main()
