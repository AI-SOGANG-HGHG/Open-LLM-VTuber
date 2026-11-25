"""Verify persistent agent identity and memory boundaries."""

from base64 import b64encode
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np

from src.open_llm_vtuber.chat_history_manager import (
    create_new_history,
    get_metadata,
    store_message,
    update_metadate,
)
from src.open_llm_vtuber.studio_persona import StudioPersona
from src.open_llm_vtuber.studio_profiles import (
    BigFive,
    PersonaPreset,
    studio_behavior_rules,
)
from src.open_llm_vtuber.studio_registry import StudioRegistry, WORKSPACE_COOKIE
from src.open_llm_vtuber.studio_registry_api import studio_registry_router
from src.open_llm_vtuber.studio_turn import (
    Affect,
    Appraisal,
    ExchangeSelection,
    MemoryMeaning,
    RECALL_METADATA,
    RecallItem,
    StudioTurnRuntime,
)

PREFERENCE = "저는 카페인에 민감해서 보리차만 마셔요."


def profile(workspace, character="first") -> StudioPersona:
    return StudioPersona(
        workspace_id=workspace,
        character_id=character,
        name="동료",
        avatar="symbol",
        preset_id="warm",
    )


class AgentRegistryTests(unittest.TestCase):
    def test_workspace_cookie_profile_revisions_copy_and_archive(self):
        with TemporaryDirectory() as directory:
            registry = StudioRegistry(Path(directory) / "studio.sqlite3")
            app = FastAPI()
            app.include_router(studio_registry_router(registry))
            workspace = uuid4()
            with TestClient(app) as owner, TestClient(app) as visitor:
                workspace_path = f"/studio/workspaces/{workspace}"
                response = owner.post(workspace_path)
                self.assertEqual(response.status_code, 204)
                self.assertIn("HttpOnly", response.headers["set-cookie"])
                self.assertEqual(visitor.post(workspace_path).status_code, 404)
                self.assertIsNone(visitor.get("/studio/workspace").json())
                original = profile(workspace).model_dump(mode="json")
                response = owner.post("/studio/agents", json=original)
                self.assertEqual(response.status_code, 200, response.text)
                created = response.json()
                agent_id = created["agent_id"]
                agent_path = f"{workspace_path}/agents/{agent_id}"
                self.assertEqual(visitor.get(agent_path).status_code, 404)
                self.assertEqual(
                    owner.post("/studio/agents", json=original).json(), created
                )
                edited = dict(
                    original,
                    name="새 이름",
                    memories=[PREFERENCE],
                    traits={**created["personality"]["traits"], "openness": 0.92},
                )
                edit = {"version": 1, "profile": edited}
                response = owner.put(f"/studio/agents/{agent_id}", json=edit)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["version"], 2)
                self.assertEqual(
                    owner.put(f"/studio/agents/{agent_id}", json=edit).status_code, 409
                )
                self.assertEqual(
                    owner.put(
                        f"/studio/agents/{agent_id}",
                        json={
                            "version": 2,
                            "profile": dict(edited, preset_id="calm"),
                        },
                    ).status_code,
                    409,
                )
                current = StudioRegistry(registry.path).get(
                    workspace, owner.cookies[WORKSPACE_COOKIE], agent_id
                )
                self.assertEqual(current.profile.memories, [PREFERENCE])
                self.assertEqual(current.personality.traits.openness, 0.92)
                copied = owner.post(
                    f"/studio/agents/{agent_id}/copy",
                    json=dict(original, character_id="copy"),
                ).json()
                self.assertNotEqual(copied["agent_id"], agent_id)
                self.assertEqual(copied["version"], 1)
                self.assertEqual(copied["profile"]["memories"], [])
                self.assertEqual(copied["personality"]["traits"]["openness"], 0.92)
                self.assertEqual(owner.delete(agent_path).status_code, 204)
                self.assertEqual(owner.get(agent_path).status_code, 404)
                index = owner.get("/studio/workspace").json()
                self.assertEqual(index["archived_characters"], ["first"])
                self.assertEqual(
                    [agent["agent_id"] for agent in index["agents"]],
                    [copied["agent_id"]],
                )


class AgentRecallTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patcher = patch(
            "src.open_llm_vtuber.chat_history_manager._conf_directory",
            side_effect=lambda conf_uid: self.root / conf_uid,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.registry = StudioRegistry(self.root / "studio.sqlite3")
        self.workspace = uuid4()
        self.token = self.registry.register_workspace(self.workspace, "")

    def test_legacy_memories_import_once_and_preserve_conversation(self):
        old_profile = profile(self.workspace)
        scope = old_profile.history_scope
        history = create_new_history(scope)
        store_message(scope, history, "human", PREFERENCE)
        previous_record = {
            "id": "earlier",
            "text": PREFERENCE,
            "occurred_at": "2026-11-21T00:00:00+00:00",
            "embedding_model": "fixture",
            "vector": b64encode(np.array([1, 0], dtype="<f4").tobytes()).decode(),
        }
        self.assertTrue(
            update_metadate(scope, history, {RECALL_METADATA: [previous_record]})
        )
        agent = self.registry.create(old_profile, self.token, legacy=True)
        self.assertEqual(agent.history_scope, scope)
        self.registry.import_memories(agent)
        self.registry.import_memories(agent)
        records = self.registry.memories(agent.agent_id, "fixture", 64)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_history_id"], history)
        self.assertEqual(
            get_metadata(scope, history)[RECALL_METADATA], [previous_record]
        )

    async def test_recall_crosses_conversations_and_stays_with_agent(self):
        first = self.registry.create(profile(self.workspace), self.token)
        second = self.registry.create(profile(self.workspace, "second"), self.token)
        original = create_new_history(first.history_scope)
        turn = await self.runtime(first).prepare(
            first.history_scope, original, PREFERENCE
        )
        await self.runtime(first).complete_async(turn)
        registry = StudioRegistry(self.registry.path)
        [record] = registry.memories(first.agent_id, "fixture", 64)
        self.assertEqual(record["source_history_id"], original)
        self.assertEqual(record["profile_version"], 1)
        self.assertEqual(record["meaning"]["kind"], "fact")
        self.assertFalse(registry.memories(first.agent_id, "other-model", 64))
        for agent, expected in [(first, [PREFERENCE]), (second, [])]:
            history = create_new_history(agent.history_scope)
            query = await self.runtime(agent, registry).prepare(
                agent.history_scope, history, "평소 무슨 음료를 마셔요?"
            )
            self.assertEqual(
                [memory["text"] for memory in query.trace["memories"]], expected
            )

    async def test_memory_survives_failed_indexing_and_reappears_in_a_new_chat(
        self,
    ) -> None:
        """Retry vectors on a later turn without losing or duplicating the source."""
        agent = self.registry.create(profile(self.workspace), self.token)
        original = create_new_history(agent.history_scope)
        runtime = self.runtime(agent)
        with patch.object(runtime.llm, "embed_texts", side_effect=TimeoutError):
            first = await runtime.prepare(agent.history_scope, original, PREFERENCE)
            self.assertTrue(first.remember)
            self.assertIsNone(first.vector)
            await runtime.complete_async(first)
            duplicate = await runtime.prepare(agent.history_scope, original, PREFERENCE)
            await runtime.complete_async(duplicate)

        registry = StudioRegistry(self.registry.path)
        self.assertEqual(
            registry.pending_embeddings(agent.agent_id, 8),
            [(first.source.id, PREFERENCE)],
        )
        self.assertEqual(registry.memories(agent.agent_id, "fixture", 64), [])
        other = self.registry.create(profile(self.workspace, "other"), self.token)
        other_history = create_new_history(other.history_scope)
        question = "제가 평소에 어떤 음료를 마신다고 했죠?"
        reply = await self.runtime(other, registry).prepare(
            other.history_scope, other_history, question
        )
        self.assertEqual(reply.trace["memories"], [])
        self.assertEqual(registry.pending_embeddings(other.agent_id, 8), [])

        new_history = create_new_history(agent.history_scope)
        reply = await self.runtime(agent, registry).prepare(
            agent.history_scope, new_history, question
        )
        self.assertEqual(
            [memory["text"] for memory in reply.trace["memories"]], [PREFERENCE]
        )
        self.assertEqual(registry.pending_embeddings(agent.agent_id, 8), [])
        [saved] = registry.memories(agent.agent_id, "fixture", 64)
        self.assertEqual(saved["id"], first.source.id)
        self.assertEqual(saved["source_history_id"], original)

    async def test_recall_accepts_an_earlier_version_id_from_a_retrieved_memory(
        self,
    ) -> None:
        """Keep the correction and its history when appraisal selects an older ID."""
        agent = self.registry.create(profile(self.workspace), self.token)
        scope = agent.history_scope
        room = create_new_history(scope)
        runtime = self.runtime(agent)
        first = await runtime.prepare(scope, room, PREFERENCE)
        await runtime.complete_async(first)
        latest_text = "정정할게요. 이제는 디카페인 커피를 가장 좋아해요."
        correction = Appraisal(
            relevant_memory_ids=[],
            corrected_memory_ids=[first.source.id],
            affect=None,
            remember=False,
        )
        with patch.object(runtime, "_appraise", return_value=correction):
            latest = await runtime.prepare(scope, room, latest_text)
        await runtime.complete_async(latest)

        new_room = create_new_history(scope)
        for ids, should_match in (
            ([first.source.id], True),
            ([first.source.id, latest.source.id, "unrelated"], True),
            (["unrelated"], False),
        ):
            with self.subTest(ids=ids):
                selection = Appraisal(
                    relevant_memory_ids=ids, affect=None, remember=False
                )
                with patch.object(runtime, "_appraise", return_value=selection):
                    query = await runtime.prepare(
                        scope, new_room, "예전에 무슨 음료를 좋아한다고 했죠?"
                    )
                memories = json.loads(query.context)["experience"]
                self.assertEqual(memories, query.trace["memories"])
                if should_match:
                    self.assertEqual(len(memories), 1)
                    [memory] = memories
                    self.assertEqual(memory["id"], latest.source.id)
                    self.assertEqual(memory["text"], latest_text)
                    self.assertEqual(memory["earlier_versions"][0]["text"], PREFERENCE)
                else:
                    self.assertEqual(memories, [])

    async def test_deadline_and_completion_facts_are_recalled_across_rooms(
        self,
    ) -> None:
        """Remember grounded facts about work in the ordinary memory store."""
        agent = self.registry.create(profile(self.workspace), self.token)
        scope = agent.history_scope
        runtime = self.runtime(agent)
        draft = "발표 준비 중인데 발표 초안을 완성했어요."
        rehearsal = "발표 리허설은 아직 못 했고 내일 해야 해요."

        for text, remember in (
            (draft, True),
            (rehearsal, True),
            ("발표 자료 공유는 어떻게 해요?", False),
        ):
            room = create_new_history(scope)
            appraisal = Appraisal(
                relevant_memory_ids=[],
                affect=None,
                remember=remember,
            )
            with patch.object(runtime, "_appraise", return_value=appraisal):
                update = await runtime.prepare(scope, room, text)
            await runtime.complete_async(update)

        records = self.registry.memories(agent.agent_id, "fixture", 64)
        self.assertEqual([record["text"] for record in records], [draft, rehearsal])
        new_room = create_new_history(scope)
        query = await self.runtime(agent).prepare(
            scope, new_room, "발표 준비에서 끝낸 것과 남은 일은 뭐야?"
        )
        self.assertCountEqual(
            [memory["text"] for memory in json.loads(query.context)["experience"]],
            [draft, rehearsal],
        )
        self.assertNotIn("task_states", query.trace)

    def test_late_index_does_not_replace_ready_or_superseded_memory(self) -> None:
        """Keep the winning embedding and skip stale work for corrected memories."""
        agent = self.registry.create(profile(self.workspace), self.token)
        old = {
            "id": "old",
            "text": PREFERENCE,
            "embedding_model": "fixture",
            "occurred_at": "2026-11-21T00:00:00+00:00",
            "vector": None,
        }
        revised = dict(
            old,
            id="revised",
            text="이제는 디카페인 커피도 마셔요.",
            occurred_at="2026-11-21T01:00:00+00:00",
        )
        self.registry.save_memory(agent.agent_id, old, ())
        self.registry.save_memory(agent.agent_id, revised, ("old",))
        self.assertEqual(
            self.registry.pending_embeddings(agent.agent_id, 8),
            [("revised", revised["text"])],
        )
        original_vector = b64encode(np.array([1, 0], dtype="<f4").tobytes()).decode()
        late_vector = b64encode(np.array([0, 1], dtype="<f4").tobytes()).decode()
        self.registry.index_pending(
            agent.agent_id, "fixture", {"revised": original_vector}
        )
        self.registry.index_pending(
            agent.agent_id, "fixture", {"old": late_vector, "revised": late_vector}
        )
        [saved] = self.registry.memories(agent.agent_id, "fixture", 64)
        self.assertEqual(saved["text"], revised["text"])
        self.assertEqual(saved["vector"], original_vector)

    async def test_recall_when_separate_relevance_check_times_out(self) -> None:
        """Pass retrieved candidates as unverified only on explicit recall requests."""
        agent = self.registry.create(profile(self.workspace), self.token)
        history = create_new_history(agent.history_scope)
        runtime = self.runtime(agent)
        seed = await runtime.prepare(agent.history_scope, history, PREFERENCE)
        await runtime.complete_async(seed)
        new_room = create_new_history(agent.history_scope)
        with patch.object(runtime, "_appraise", side_effect=TimeoutError):
            recall = await runtime.prepare(
                agent.history_scope, new_room, "제가 어떤 음료를 마신다고 했죠?"
            )
            casual = await runtime.prepare(
                agent.history_scope, new_room, "오늘은 음료 이야기나 할까요?"
            )
        self.assertEqual(recall.trace["retrieval"], "ok")
        self.assertEqual(recall.trace["appraisal"], "unavailable")
        self.assertEqual(recall.trace["memories"], [])
        context = json.loads(recall.context)
        self.assertEqual(context["experience"], [])
        candidates = context["unverified_experience"]
        self.assertEqual([item["text"] for item in candidates], [PREFERENCE])
        self.assertEqual(recall.trace["unverified_memories"], candidates)
        self.assertNotIn("unverified_experience", json.loads(casual.context))

    def test_big_five_sampling_and_experience_ranking(self):
        traits = BigFive(**dict.fromkeys(BigFive.model_fields, 1))
        data = profile(self.workspace).model_copy(update={"traits": traits})
        agent = self.registry.create(data, self.token)
        runtime = self.runtime(agent)
        self.assertTrue(
            all(rule.direction == "high" for rule in runtime._active_rules())
        )
        vector = np.array([1, 0], dtype=np.float32)
        journal = RecallItem(
            "event",
            "함께 프로젝트를 끝낸 날",
            "user_turn",
            meaning=MemoryMeaning(
                kind="experience", importance=1, axes={"agreeableness": "high"}
            ),
        )
        preference = RecallItem(
            "fact", PREFERENCE, "user_turn", meaning=MemoryMeaning(kind="fact")
        )
        ranked = runtime._rank(
            vector, [(preference, vector), (journal, vector)], 2, persona_weighted=True
        )
        self.assertEqual(ranked, [journal, preference])
        self.assertEqual(
            runtime._rank(vector, [(journal, vector[::-1])], 1, persona_weighted=True),
            [],
        )

    def test_vad_changes_rank_only_for_relevant_experiences(self):
        agent = self.registry.create(profile(self.workspace), self.token)
        runtime = self.runtime(agent)
        vector = np.array([1, 0], dtype=np.float32)
        now = datetime.now(timezone.utc).isoformat()
        happy = RecallItem(
            "happy",
            "환호하며 끝낸 발표",
            "user_turn",
            now,
            meaning=MemoryMeaning(kind="experience"),
            event_affect=Affect(valence=0.9, arousal=0.6, dominance=0.7),
        )
        sad = RecallItem(
            "sad",
            "실망하며 끝낸 발표",
            "user_turn",
            now,
            meaning=MemoryMeaning(kind="experience"),
            event_affect=Affect(valence=-0.9, arousal=0.6, dominance=0.7),
        )
        for current, expected in ((happy.event_affect, happy), (sad.event_affect, sad)):
            self.assertEqual(
                runtime._rank(
                    vector,
                    [(happy, vector), (sad, vector)],
                    1,
                    persona_weighted=True,
                    affect=current,
                ),
                [expected],
            )
            self.assertEqual(
                runtime._rank(
                    vector,
                    [(expected, vector[::-1])],
                    1,
                    persona_weighted=True,
                    affect=current,
                ),
                [],
            )
        old = RecallItem(
            "old",
            happy.text,
            happy.source,
            (datetime.now(timezone.utc) - timedelta(days=90)).isoformat(),
            meaning=happy.meaning,
            event_affect=happy.event_affect,
        )
        self.assertGreater(
            runtime._affective_weight(happy, happy.event_affect),
            runtime._affective_weight(old, happy.event_affect),
        )

    def test_optional_trait_labels_do_not_discard_the_event_appraisal(self):
        appraisal = Appraisal.model_validate(
            {
                "relevant_memory_ids": [],
                "remember": True,
                "affect": None,
                "memory_meaning": {
                    "kind": "experience",
                    "axes": {
                        "agreeableness": "high",
                        "neuroticism": "medium",
                        "openness": 0.8,
                    },
                },
            }
        )
        self.assertEqual(appraisal.memory_meaning.axes, {"agreeableness": "high"})

    async def test_explicit_goal_searches_once_more_for_missing_evidence(self):
        agent = self.registry.create(profile(self.workspace), self.token)
        runtime = self.runtime(agent)
        now = datetime.now(timezone.utc)
        for event_id, text, vector in (
            ("draft", "발표 초안을 완성했다", [1, 0]),
            ("rehearsal", "리허설은 내일 저녁에 해야 한다", [0, 1]),
            ("rehearsal-note", "발표 리허설은 강당에서 한다", [0.8, 0.6]),
        ) + tuple(
            (f"filler-{index}", f"다른 대화 {index}", [-1, 0]) for index in range(64)
        ):
            recorded = now
            if event_id == "rehearsal":
                recorded -= timedelta(days=1)
            elif event_id.startswith("filler-"):
                recorded -= timedelta(hours=1)
            self.registry.save_memory(
                agent.agent_id,
                {
                    "id": event_id,
                    "text": text,
                    "occurred_at": recorded.isoformat(),
                    "embedding_model": "fixture",
                    "vector": runtime._encode_vector(
                        np.array(vector, dtype=np.float32)
                    ),
                },
                (),
            )
        llm = runtime.llm
        llm.embed_texts = AsyncMock(
            side_effect=lambda _, texts: [
                [0, 1] if text == "발표 리허설 상태" else [1, 0] for text in texts
            ]
        )
        room = create_new_history(agent.history_scope)
        with patch.object(
            runtime,
            "_appraise",
            new=AsyncMock(
                return_value=Appraisal(
                    relevant_memory_ids=["draft"],
                    affect=None,
                    remember=False,
                    next_recall_query="발표 리허설 상태",
                )
            ),
        ):
            turn = await runtime.prepare(
                agent.history_scope, room, "전에 정한 거, 제 연습 일정이 필요해요."
            )
        self.assertEqual(turn.trace["recall_steps"], 2)
        self.assertIsNone(turn.trace["recall_redirection"])
        self.assertEqual([item["id"] for item in turn.trace["memories"]], ["draft"])
        self.assertEqual(
            [item["id"] for item in turn.trace["unverified_memories"]],
            ["rehearsal", "rehearsal-note"],
        )

    async def test_recall_gate_redirects_only_the_single_followup(self):
        agent = self.registry.create(profile(self.workspace), self.token)
        runtime = self.runtime(agent)
        now = datetime.now(timezone.utc).isoformat()
        cue_text = "발표 무대 리허설을 하다가 조명 순서를 바꾸기로 했다. " + (
            "메모" * 30
        )
        cue = cue_text[:60].strip()
        semantic_query = "발표 리허설 일정"
        scenarios = (
            ("draft", "발표 초안 완성", [1, 0, 0]),
            ("slides", "발표 슬라이드 완성", [1, 0, 0]),
            ("intro", "발표 도입부 확정", [1, 0, 0]),
            ("cue", cue_text, [0.8, 0, 0.6]),
            ("rehearsal", "리허설은 내일 저녁에 해야 한다", [0, 1, 0]),
            ("lights", "조명 전환 연습은 아직 하지 않았다", [0, 0, 1]),
        )
        for memory_id, memory_text, coordinates in scenarios:
            record = {
                "id": memory_id,
                "text": memory_text,
                "occurred_at": now,
                "embedding_model": "fixture",
                "vector": runtime._encode_vector(
                    np.array(coordinates, dtype=np.float32)
                ),
            }
            if memory_id in ("cue", "rehearsal"):
                record.update(
                    meaning={"kind": "experience"},
                    event_affect=Affect(
                        valence=0.8, arousal=0.7, dominance=0.8
                    ).model_dump(),
                )
            self.registry.save_memory(agent.agent_id, record, ())
        runtime.llm.embed_texts = AsyncMock(
            side_effect=lambda _, texts: [
                [0, 0, 1]
                if item == cue
                else [0, 1, 0]
                if item == semantic_query
                else [1, 0, 0]
                for item in texts
            ]
        )
        appraisal = Appraisal(
            relevant_memory_ids=["draft"],
            affect=None,
            remember=False,
            next_recall_query=semantic_query,
        )
        room = create_new_history(agent.history_scope)
        for draw, followup, expected in (
            (0.0, cue, ["cue", "lights"]),
            (0.999999, semantic_query, ["rehearsal"]),
        ):
            with (
                self.subTest(draw=draw),
                patch.object(
                    runtime, "_appraise", new=AsyncMock(return_value=appraisal)
                ),
                patch("src.open_llm_vtuber.studio_turn.random", return_value=draw),
            ):
                runtime.llm.embed_texts.reset_mock()
                turn = await runtime.prepare(
                    agent.history_scope, room, "발표 준비에서 뭐가 남았지?"
                )
                self.assertEqual(runtime.llm.embed_texts.await_count, 2)
                self.assertEqual(runtime.llm.embed_texts.await_args.args[1], [followup])
                self.assertEqual(turn.trace["recall_steps"], 2)
                self.assertEqual(turn.trace["recall_redirection"]["memory_id"], "cue")
                self.assertEqual(
                    turn.trace["recall_redirection"]["redirected"], draw == 0.0
                )
                self.assertEqual(
                    [item["id"] for item in turn.trace["memories"]], ["draft"]
                )
                self.assertEqual(
                    [item["id"] for item in turn.trace["unverified_memories"]], expected
                )
        with (
            patch.object(
                runtime,
                "_appraise",
                new=AsyncMock(
                    return_value=appraisal.model_copy(
                        update={"next_recall_query": None}
                    )
                ),
            ),
            patch.object(
                runtime, "_redirection_candidate", wraps=runtime._redirection_candidate
            ) as redirect,
        ):
            turn = await runtime.prepare(
                agent.history_scope, room, "오늘은 날씨가 화창해."
            )
        redirect.assert_not_called()
        self.assertEqual(turn.trace["recall_steps"], 1)
        self.assertIsNone(turn.trace["recall_redirection"])

    def test_recall_gate_probability_increases_with_arousal_and_neuroticism(self):
        def runtime_with_trait(character, neuroticism):
            traits = BigFive(
                **{
                    **dict.fromkeys(BigFive.model_fields, 0.5),
                    "neuroticism": neuroticism,
                }
            )
            data = profile(self.workspace, character).model_copy(
                update={"traits": traits}
            )
            return self.runtime(self.registry.create(data, self.token))

        calm = runtime_with_trait("calm", 0.0)
        sensitive = runtime_with_trait("sensitive", 1.0)
        quiet, activated = Affect(arousal=0.0), Affect(arousal=0.9)
        self.assertAlmostEqual(calm._redirection_probability(0.5, quiet), 0.5)
        self.assertGreater(
            calm._redirection_probability(0.5, activated),
            calm._redirection_probability(0.5, quiet),
        )
        self.assertGreater(
            sensitive._redirection_probability(0.5, quiet),
            calm._redirection_probability(0.5, quiet),
        )

    async def test_completed_reply_persists_grounded_character_commitment(self):
        agent = self.registry.create(profile(self.workspace), self.token)
        runtime = self.runtime(agent)
        room = create_new_history(agent.history_scope)
        turn = await runtime.prepare(
            agent.history_scope, room, "초안을 나중에 가져올게요."
        )
        reply = "다음에 초안을 가져오면 구조부터 검토할게요."
        with patch.object(
            runtime,
            "_decision",
            new=AsyncMock(
                return_value=ExchangeSelection(
                    response_evidence=reply,
                    kind="commitment",
                )
            ),
        ):
            await runtime.complete_async(turn, reply)
        [pending] = self.registry.pending_embeddings(agent.agent_id, 8)
        self.assertEqual(pending, (turn.source.id, f"{turn.source.text}\n{reply}"))
        await runtime.prepare(agent.history_scope, room, "지난번에 뭐라고 했지?")
        [memory] = self.registry.memories(agent.agent_id, "fixture", 8)
        self.assertEqual(memory["assistant_excerpt"], reply)
        self.assertEqual(memory["assistant_memory_kind"], "commitment")
        self.assertEqual(memory["text"], turn.source.text)

    async def test_grounded_reply_affect_is_saved_with_the_experience(self):
        agent = self.registry.create(profile(self.workspace), self.token)
        runtime = self.runtime(agent)
        room = create_new_history(agent.history_scope)
        remark = "함께 준비한 발표가 성공적으로 마무리됐어요."
        with patch.object(
            runtime,
            "_appraise",
            new=AsyncMock(
                return_value=Appraisal(
                    relevant_memory_ids=[],
                    remember=True,
                    affect_evidence=remark,
                    affect=Affect(valence=0.8, arousal=0.6, dominance=0.7),
                    memory_meaning=MemoryMeaning(
                        kind="experience", experiencer="shared"
                    ),
                )
            ),
        ):
            turn = await runtime.prepare(agent.history_scope, room, remark)
        reply = "함께 해냈다는 게 저도 정말 기뻐요."
        with patch.object(
            runtime,
            "_decision",
            new=AsyncMock(
                return_value=ExchangeSelection(
                    response_affect=Affect(valence=0.4, arousal=0.4, dominance=0.5),
                    response_affect_evidence=reply,
                )
            ),
        ):
            await runtime.complete_async(turn, reply)
        [memory] = self.registry.memories(agent.agent_id, "fixture", 8)
        self.assertEqual(
            memory["event_affect"], {"valence": 0.6, "arousal": 0.5, "dominance": 0.6}
        )

    def runtime(self, agent, registry=None) -> StudioTurnRuntime:
        return StudioTurnRuntime(
            agent.agent_id,
            PersonaPreset(
                **agent.personality.model_dump(), rules=studio_behavior_rules()
            ),
            [],
            RecallLLM(),
            "fixture",
            registry=registry or self.registry,
        )


class RecallLLM:
    async def embed_texts(self, model, texts):
        return [[1, 0] for _ in texts]

    async def chat_completion(self, messages, system):
        if system.startswith("Select applicable"):
            yield '{"matches":[]}'
            return
        request = json.loads(messages[0]["content"])
        save = request["input"] == PREFERENCE
        yield json.dumps(
            {
                "relevant_memory_ids": [
                    memory["id"] for memory in request["memory_candidates"]
                ],
                "affect": None,
                "remember": save,
                "memory_meaning": {"kind": "fact"} if save else None,
            }
        )
