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
from src.open_llm_vtuber.studio_profiles import (
    BEHAVIOR_RULES_FILE,
    BigFive,
    PersonaPreset,
    PresetCatalog,
    PresetProfile,
    load_behavior_rules,
    studio_presets,
)
from src.open_llm_vtuber.studio_tasks import TASK_METADATA
from src.open_llm_vtuber.studio_turn import AFFECT_METADATA, RECALL_METADATA
from src.open_llm_vtuber.websocket_handler import WebSocketHandler

HELPFUL = "beck2022_high_agre__sociality__helpful__118"
LITTLE_SYMPATHY = "beck2022_low_agre__adversity__little_sympathy__129"
WARMTH_IN_GROUP = "beck2022_high_agre__positivity__rude__114"
ORGANIZED_CONVERSATION = "beck2022_high_cons__sociality__efficient__044"
HELP_SCENARIO = "친구가 심하게 비판받은 뒤 네게 도움을 청한다면 어떻게 반응할 거야?"
GROUP_SCENARIO = (
    "편안한 모임에서 여러 사람과 함께 있고 대화해야 한다면 어떻게 행동할 거야?"
)


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
        self.assertEqual(reviewer.background, coach.background)
        self.assertEqual(reviewer.values, coach.values)
        self.assertEqual(
            reviewer.traits.model_dump(exclude={"agreeableness"}),
            coach.traits.model_dump(exclude={"agreeableness"}),
        )
        self.assertLess(reviewer.traits.agreeableness, coach.traits.agreeableness)
        reviewer_rules = {rule.id: rule for rule in reviewer.rules}
        coach_rules = {rule.id: rule for rule in coach.rules}
        self.assertEqual(
            [rule for rule in reviewer.rules if rule.trait != "agreeableness"],
            [rule for rule in coach.rules if rule.trait != "agreeableness"],
        )
        self.assertTrue(
            all(
                reviewer_rules[rule_id].direction == "low"
                for rule_id in reviewer_rules.keys() - coach_rules.keys()
            )
        )
        self.assertIn(LITTLE_SYMPATHY, reviewer_rules)
        self.assertNotIn(LITTLE_SYMPATHY, coach_rules)
        self.assertIn(HELPFUL, coach_rules)
        self.assertNotIn(HELPFUL, reviewer_rules)

    def test_big_five_axis_selects_only_its_own_behavior_and_requires_valid_scores(
        self,
    ):
        with open("config_templates/studio-personas.yaml", encoding="utf-8") as file:
            catalog = PresetCatalog.model_validate(yaml.safe_load(file))
        rules = load_behavior_rules(Path("config_templates") / BEHAVIOR_RULES_FILE)
        self.assertEqual(len(rules), 166)
        scores = {axis: 0.4 for axis in BigFive.model_fields}
        profile = catalog.presets["direct-reviewer"]
        baseline = PersonaPreset.from_profile(
            profile.model_copy(update={"traits": BigFive.model_validate(scores)}),
            rules,
        )
        baseline_ids = {rule.id for rule in baseline.rules}
        for axis in scores:
            with self.subTest(axis=axis):
                changed = PersonaPreset.from_profile(
                    profile.model_copy(
                        update={"traits": BigFive.model_validate({**scores, axis: 0.8})}
                    ),
                    rules,
                )
                changed_ids = {rule.id for rule in changed.rules}
                self.assertEqual(
                    changed_ids - baseline_ids,
                    {
                        rule.id
                        for rule in rules
                        if rule.trait == axis and rule.direction == "high"
                    },
                )
                self.assertEqual(
                    baseline_ids - changed_ids,
                    {
                        rule.id
                        for rule in rules
                        if rule.trait == axis and rule.direction == "low"
                    },
                )
                with self.assertRaises(ValidationError):
                    BigFive.model_validate({**scores, axis: 1.1})

    def test_a_direction_can_have_a_rule_without_a_matching_situation(self):
        rules = load_behavior_rules(Path("config_templates") / BEHAVIOR_RULES_FILE)
        (high_rule,) = tuple(rule for rule in rules if rule.id == HELPFUL)
        profile = studio_presets()["direct-reviewer"].model_dump(exclude={"rules"})
        self.assertEqual(
            PersonaPreset.from_profile(PresetProfile(**profile), (high_rule,)).rules, ()
        )
        profile["traits"]["agreeableness"] = 0.8
        self.assertEqual(
            PersonaPreset.from_profile(PresetProfile(**profile), (high_rule,)).rules,
            (high_rule,),
        )

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
        self.assertNotIn('"traits"', system_prompt)
        self.assertEqual(
            agent.enable_studio_runtime.call_args.args[:2],
            ("calm", studio_presets()["calm"]),
        )

    def test_scope_is_stable_and_separates_workspace_and_character(self):
        first = StudioPersona(**payload())
        same = StudioPersona(**{**first.model_dump(), "avatar": "ivory-crown"})
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
        self.generation_system = None
        self.appraisal_request = None
        self.embedding_calls = []
        self.fail_embedding = False
        self.invalid_appraisal = False
        self.task_update = None
        self.correct_beverage = False
        self.affect_rating = {"valence": 0.5, "arousal": 0.5, "dominance": 0.75}

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
        if system.startswith("Select applicable behavior conditions"):
            data = json.loads(messages[0]["content"])
            expected = {
                HELP_SCENARIO: {HELPFUL, LITTLE_SYMPATHY},
                GROUP_SCENARIO: {WARMTH_IN_GROUP, ORGANIZED_CONVERSATION},
            }.get(data["input"], set())
            matching_situations = {
                rule.situation
                for rule in load_behavior_rules(
                    Path("config_templates") / BEHAVIOR_RULES_FILE
                )
                if rule.id in expected
            }
            yield json.dumps(
                {
                    "matches": [
                        {"number": int(index), "evidence": data["input"]}
                        for group in data["condition_groups"]
                        for index, situation in group.items()
                        if situation in matching_situations
                    ]
                }
            )
            return
        if system.startswith("Evaluate the fictional character"):
            if self.invalid_appraisal:
                yield '{"affect": {"valence": 10}, "remember": false}'
                return
            self.appraisal_request = json.loads(messages[0]["content"])
            text = self.appraisal_request["input"]
            neutral_preference = "카페인" in text and "보리차" in text
            deadline_disclosure = "내일이 발표인데" in text
            memory_candidates = self.appraisal_request["memory_candidates"]
            recent_dialogue = self.appraisal_request["recent_dialogue"]
            beverage_query = "음료" in text or (
                text.startswith("그거")
                and any("음료" in item["text"] for item in recent_dialogue)
            )
            yield json.dumps(
                {
                    "relevant_memory_ids": [
                        memory["id"]
                        for memory in memory_candidates
                        if (beverage_query and memory["source"] == "user_turn")
                        or ("발표" in text and "발표" in memory["text"])
                    ],
                    "affect": None if neutral_preference else self.affect_rating,
                    "affect_evidence": None
                    if neutral_preference or text.endswith("?")
                    else text,
                    "use_recent_dialogue": text.startswith("그거"),
                    "remember": deadline_disclosure
                    or neutral_preference
                    or "기억해 줘" in text,
                    "relevant_task_ids": [
                        task["id"]
                        for task in self.appraisal_request["stored_tasks"]
                        if "발표" in text
                    ],
                    "task_update": self.task_update,
                    "corrected_memory_ids": [
                        memory["id"]
                        for memory in memory_candidates
                        if "보리차" in memory["text"]
                    ]
                    if self.correct_beverage
                    else [],
                }
            )
            return
        self.request = messages
        self.generation_system = system
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

    def connect_agent(
        self, preset_id="calm", notes=("캠퍼스 셔틀은 네 시에 출발한다.",)
    ):
        preset = studio_presets()[preset_id]
        self.llm = RecordedStudioLLM()
        self.agent = BasicMemoryAgent(
            llm=self.llm,
            system=preset.system_prompt("서강이"),
            live2d_model=self.context.live2d_model,
            tts_preprocessor_config=self.context.character_config.tts_preprocessor_config,
            segment_method="regex",
        )
        self.agent.enable_studio_runtime(preset_id, preset, notes, "fixture")
        self.context.agent_engine = self.agent

    def match_rule_situations(self, question, *rule_ids):
        matches = {question}
        matches.update(
            rule.situation
            for rule in self.agent.studio_runtime.preset.rules
            if rule.id in rule_ids
        )
        return patch.object(
            self.llm,
            "embed_texts",
            side_effect=lambda _, texts: [
                [1, 0, 0] if text in matches else [0, 0, 1] for text in texts
            ],
        )

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
        self.assertEqual(trace["affect"], trace["previous_affect"])
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
        self.assertEqual(
            trace["previous_affect"], metadata[AFFECT_METADATA]["calm"]["affect"]
        )
        self.assertEqual([row["text"] for row in trace["memories"]], [original])

        self.assertTrue(delete_history(self.scope, history_uid))
        self.assertEqual(get_metadata(self.scope, history_uid), {})
        after = await self.agent.studio_runtime.prepare(
            self.scope, history_uid, "어떤 음료를 좋아하지?"
        )
        self.assertEqual(after.trace["memories"], [])

    async def test_rules_rank_separately_and_provider_failures_allow_a_reply(self):
        with self.match_rule_situations(HELP_SCENARIO, HELPFUL):
            events = await self.turn(HELP_SCENARIO)
        valid = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertIn(HELPFUL, [rule["id"] for rule in valid["rules"]])
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
        text = "카페인에 민감해서 보리차만 마셔요."
        preset = studio_presets()["supportive-coach"]
        notes = tuple(f"노트 {index}" for index in range(50))
        self.connect_agent("supportive-coach", notes)
        with patch.object(
            self.llm,
            "embed_texts",
            side_effect=lambda _, texts: [[1, 0, 0]] * len(texts),
        ) as embed:
            events = await self.turn(text)
        self.assertEqual(
            [len(call.args[1]) for call in embed.await_args_list],
            [
                100,
                len({rule.situation for rule in preset.rules}) + len(notes) + 1 - 100,
            ],
        )

        trace = next(e for e in events if e["type"] == "studio-turn-context")
        ids = set(trace["rule_candidate_ids"])
        expected = set()
        for axis in BigFive.model_fields:
            expected.update(
                [rule.id for rule in preset.rules if rule.trait == axis][:4]
            )
        self.assertEqual(ids, expected)
        self.assertEqual(trace["appraisal"], "ok")
        self.assertEqual(trace["affect"], trace["previous_affect"])
        self.assertEqual(trace["rules"], [])
        self.assertNotIn(
            "이번 턴에 적용할 상황별 행동 규칙", self.llm.generation_system
        )
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

    async def test_interruption_does_not_commit_affect_or_index_the_turn(self):
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
        self.assertEqual(trace["previous_affect"]["valence"], 0)

    async def test_affect_restores_in_same_preset_while_new_preset_and_history_start_neutral(
        self,
    ):
        history_uid = self.context.history_uid
        self.llm.affect_rating = {"valence": -0.75, "arousal": 0.8, "dominance": 0.25}
        events = await self.turn("내일이 발표인데 아직 초안도 작성하지 못했어.")
        pressure = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertAlmostEqual(pressure["affect"]["valence"], -0.3)

        self.connect_agent()
        self.agent.set_memory_from_history(self.scope, history_uid)
        events = await self.turn("나는 카페인에 민감해서 보리차만 마셔.")
        neutral = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertEqual(neutral["previous_affect"], pressure["affect"])
        self.assertEqual(neutral["affect"], pressure["affect"])
        self.assertEqual(neutral["affect_event_id"], pressure["affect_event_id"])

        self.llm.affect_rating = {"valence": 0.8, "arousal": 0.2, "dominance": 0.8}
        events = await self.turn("발표 준비를 모두 끝냈어.")
        recovery = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertEqual(recovery["previous_affect"], pressure["affect"])
        self.assertGreater(recovery["affect"]["valence"], pressure["affect"]["valence"])

        self.connect_agent("direct-reviewer")
        self.agent.set_memory_from_history(self.scope, history_uid)
        events = await self.turn("나는 카페인에 민감해서 보리차만 마셔.")
        switched = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertEqual(
            switched["previous_affect"], {"valence": 0, "arousal": 0, "dominance": 0.5}
        )
        self.assertEqual(
            get_metadata(self.scope, history_uid)[AFFECT_METADATA]["calm"]["affect"],
            recovery["affect"],
        )

        self.connect_agent()
        self.context.history_uid = create_new_history(self.scope)
        events = await self.turn("나는 카페인에 민감해서 보리차만 마셔.")
        fresh = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertEqual(fresh["previous_affect"], switched["previous_affect"])

    async def test_appraisal_timeout_keeps_the_last_saved_affect_and_still_replies(
        self,
    ):
        history_uid = self.context.history_uid
        await self.turn("발표 준비가 막막해.")
        saved = get_metadata(self.scope, history_uid)[AFFECT_METADATA]
        with patch.object(
            self.agent.studio_runtime, "_appraise", side_effect=TimeoutError
        ):
            events = await self.turn("같이 얘기해 볼까?")
        trace = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertEqual(trace["appraisal"], "unavailable")
        self.assertEqual(trace["previous_affect"], saved["calm"]["affect"])
        self.assertEqual(trace["affect"], trace["previous_affect"])
        self.assertTrue(any(event["type"] == "text-response" for event in events))
        self.assertEqual(get_metadata(self.scope, history_uid)[AFFECT_METADATA], saved)

    async def test_older_completion_cannot_replace_a_newer_affect_snapshot(self):
        history_uid = self.context.history_uid
        runtime = self.agent.studio_runtime
        older = await runtime.prepare(self.scope, history_uid, "서둘러야겠어.")
        self.llm.affect_rating = {"valence": -0.6, "arousal": 0.75, "dominance": 0.2}
        newer = await runtime.prepare(self.scope, history_uid, "시간이 부족해졌어.")
        runtime.complete(newer)
        runtime.complete(older)
        saved = get_metadata(self.scope, history_uid)[AFFECT_METADATA]["calm"]
        self.assertEqual(saved["event_id"], newer.source.id)
        self.assertEqual(saved["affect"], newer.trace["affect"])

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

    async def test_followup_query_uses_recent_topic_without_an_extra_embedding_request(
        self,
    ):
        preference = "내가 좋아하는 음료는 보리차야. 기억해 줘."
        await self.turn(preference)
        before = len(self.llm.embedding_calls)
        events = await self.turn("그거 뭐였지?")
        self.assertEqual(len(self.llm.embedding_calls), before + 1)
        _, queries = self.llm.embedding_calls[-1]
        self.assertEqual(queries[0], "그거 뭐였지?")
        self.assertIn(preference, queries[1])
        trace = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertEqual([memory["text"] for memory in trace["memories"]], [preference])

    async def test_explicit_correction_returns_latest_memory_and_keeps_earlier_evidence(
        self,
    ):
        history_uid = self.context.history_uid
        old = "나는 카페인에 민감해서 보리차만 마셔. 기억해 줘."
        latest = "그건 정정할게. 이제 디카페인 커피도 마셔."
        await self.turn(old)
        self.llm.correct_beverage = True
        await self.turn(latest)
        original, replacement = get_metadata(self.scope, history_uid)[RECALL_METADATA]
        self.assertEqual(original["superseded_by"], replacement["id"])
        self.assertEqual([original["text"], replacement["text"]], [old, latest])

        self.connect_agent()
        self.agent.set_memory_from_history(self.scope, history_uid)
        events = await self.turn("내가 평소 어떤 음료를 마신다고 했지?")
        trace = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        (recalled,) = trace["memories"]
        self.assertEqual(recalled["text"], latest)
        self.assertEqual(recalled["earlier_versions"][0]["text"], old)

    async def test_same_situation_uses_each_presets_own_paper_rule(self):
        behaviors = []
        for preset_id, expected_id in (
            ("direct-reviewer", LITTLE_SYMPATHY),
            ("supportive-coach", HELPFUL),
        ):
            self.context.history_uid = create_new_history(self.scope)
            self.connect_agent(preset_id)
            with self.match_rule_situations(HELP_SCENARIO, expected_id):
                events = await self.turn(HELP_SCENARIO)
            trace = next(
                event for event in events if event["type"] == "studio-turn-context"
            )
            rule = next(rule for rule in trace["rules"] if rule["id"] == expected_id)
            self.assertEqual(rule["provenance"]["dataset_id"], "0060_beck")
            self.assertEqual(trace["affect"], trace["previous_affect"])
            behaviors.append(rule["behavior"])
        self.assertIn("공감을 보이지 않으며", behaviors[0])
        self.assertIn("구체적으로 돕고", behaviors[1])

    async def test_two_axes_reach_the_same_generation_prompt(self):
        self.connect_agent("supportive-coach")
        with self.match_rule_situations(
            GROUP_SCENARIO, WARMTH_IN_GROUP, ORGANIZED_CONVERSATION
        ):
            events = await self.turn(GROUP_SCENARIO)
        trace = next(
            event for event in events if event["type"] == "studio-turn-context"
        )
        self.assertEqual(
            {rule["id"] for rule in trace["rules"]},
            {WARMTH_IN_GROUP, ORGANIZED_CONVERSATION},
        )
        system = self.llm.generation_system
        rules = json.loads(system.split("이번 턴에 적용할 상황별 행동 규칙\n", 1)[1])
        self.assertEqual(
            rules,
            [
                {"situation": rule["situation"], "behavior": rule["behavior"]}
                for rule in trace["rules"]
            ],
        )
        self.assertNotIn('"agreeableness"', system)
        self.assertNotIn('"conscientiousness"', system)
        await self.turn("안녕하세요.")
        self.assertNotIn(
            "이번 턴에 적용할 상황별 행동 규칙", self.llm.generation_system
        )

    async def test_rule_selection_survives_state_appraisal_failure(self):
        self.llm.invalid_appraisal = True
        with self.match_rule_situations(HELP_SCENARIO, HELPFUL):
            events = await self.turn(HELP_SCENARIO)
        trace = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertEqual(trace["appraisal"], "unavailable")
        self.assertEqual(trace["rule_selection"], "ok")
        self.assertEqual([rule["id"] for rule in trace["rules"]], [HELPFUL])

    async def test_new_topic_does_not_forward_recent_messages(self):
        await self.turn("내일이 발표인데 아직 초안도 작성하지 못했어.")
        await self.turn("나는 카페인에 민감해서 보리차만 마셔.")
        events = await self.turn("내가 어떤 음료를 마신다고 했지?")
        trace = next(e for e in events if e["type"] == "studio-turn-context")
        self.assertFalse(trace["used_recent_dialogue"])
        self.assertEqual(trace["affect"], trace["previous_affect"])
        self.assertEqual(len(self.llm.request), 1)
        self.assertNotIn("발표", str(self.llm.request))

    async def test_static_rule_vectors_are_shared_but_notes_are_per_connection(self):
        provider = f"https://fixture.invalid/{uuid4()}"
        self.connect_agent(notes=("첫 연결의 기억",))
        self.llm.base_url = provider
        await self.turn("안녕.")
        self.assertGreater(len(self.llm.embedding_calls[0][1]), 2)
        self.connect_agent(notes=("두 번째 연결의 기억",))
        self.llm.base_url = provider
        await self.turn("반가워.")
        self.assertEqual(
            self.llm.embedding_calls, [("fixture", ["반가워.", "두 번째 연결의 기억"])]
        )


if __name__ == "__main__":
    logger.remove()
    unittest.main()
