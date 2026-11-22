"""Verify persistent agent identity and memory boundaries."""

from base64 import b64encode
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
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
from src.open_llm_vtuber.studio_tasks import TaskUpdate
from src.open_llm_vtuber.studio_turn import (
    Appraisal,
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

    async def test_validated_task_updates_are_recalled_across_rooms(
        self,
    ) -> None:
        """Save grounded task updates even when appraisal declines generic recall."""
        agent = self.registry.create(profile(self.workspace), self.token)
        scope = agent.history_scope
        runtime = self.runtime(agent)
        draft = "발표 준비 중인데 발표 초안을 완성했어요."
        rehearsal = "발표 리허설은 아직 못 했고 내일 해야 해요."

        for text, title, status, evidence in (
            (draft, "발표 초안", "completed", "발표 초안을 완성했어요"),
            (rehearsal, "발표 리허설", "not_started", "아직 못 했고 내일 해야 해요"),
            (
                "발표 자료 공유는 어떻게 해요?",
                "발표 자료 공유",
                "completed",
                "자료 공유를 완료했어요",
            ),
        ):
            room = create_new_history(scope)
            appraisal = Appraisal(
                relevant_memory_ids=[],
                affect=None,
                remember=False,
                task_update=TaskUpdate(
                    task_id=None, title=title, status=status, evidence=evidence
                ),
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
        self.assertEqual(query.trace["task_states"], [])

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
        """Offer candidates only on a recall request and mark them as unverified."""
        agent = self.registry.create(profile(self.workspace), self.token)
        history = create_new_history(agent.history_scope)
        runtime = self.runtime(agent)
        seed = await runtime.prepare(agent.history_scope, history, PREFERENCE)
        await runtime.complete_async(seed)
        with patch.object(runtime, "_appraise", side_effect=TimeoutError):
            recall = await runtime.prepare(
                agent.history_scope, history, "제가 어떤 음료를 마신다고 했죠?"
            )
            unrelated = await runtime.prepare(
                agent.history_scope, history, "발표 준비는 지금 어때?"
            )
        self.assertEqual(recall.trace["appraisal"], "unavailable")
        self.assertEqual(recall.trace["memories"], [])
        self.assertEqual(
            [
                item["text"]
                for item in json.loads(recall.context)["unverified_experience"]
            ],
            [PREFERENCE],
        )
        self.assertEqual(
            recall.trace["unverified_memories"],
            json.loads(recall.context)["unverified_experience"],
        )
        self.assertNotIn("unverified_experience", json.loads(unrelated.context))

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
