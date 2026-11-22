"""Persist Studio identities, profile revisions, and agent-owned memories."""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
from typing import Iterator
from uuid import UUID, uuid4

from .chat_history_manager import get_history_list, get_metadata
from .studio_persona import StudioPersona
from .studio_profiles import BigFive, PresetProfile, studio_presets

WORKSPACE_COOKIE = "studio_workspace"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    credential TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS workspace_credential ON workspaces(credential);
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
    character_id TEXT NOT NULL,
    history_scope TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL,
    memory_imported INTEGER NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    UNIQUE(workspace_id, character_id)
);
CREATE TABLE IF NOT EXISTS agent_profiles (
    agent_id TEXT NOT NULL REFERENCES agents(id),
    version INTEGER NOT NULL,
    profile TEXT NOT NULL,
    personality TEXT NOT NULL,
    PRIMARY KEY(agent_id, version)
);
CREATE TABLE IF NOT EXISTS agent_memories (
    agent_id TEXT NOT NULL REFERENCES agents(id),
    event_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    text TEXT NOT NULL,
    payload TEXT NOT NULL,
    superseded_by TEXT,
    PRIMARY KEY(agent_id, event_id)
);
CREATE INDEX IF NOT EXISTS agent_memory_lookup
    ON agent_memories(agent_id, embedding_model, occurred_at);
"""


class AgentNotFound(LookupError):
    """An agent or workspace is unavailable to the supplied credential."""


class ProfileConflict(ValueError):
    """A profile write used an older version or a different original preset."""


@dataclass(frozen=True)
class RegisteredAgent:
    """Bind a public profile revision to its permanent agent and history identities."""

    agent_id: str
    history_scope: str
    profile: StudioPersona
    personality: PresetProfile
    memory_imported: bool

    def public(self) -> dict:
        """Return the current character metadata for its workspace."""
        return {
            "agent_id": self.agent_id,
            "version": self.personality.version,
            "profile": self.profile.model_dump(mode="json"),
            "personality": self.personality.model_dump(mode="json"),
        }


class StudioRegistry:
    """Use short SQLite transactions with one connection per operation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as database:
            database.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.path, timeout=5)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA foreign_keys = ON")
        return database

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with closing(self._connect()) as database, database:
            database.execute("BEGIN IMMEDIATE")
            yield database

    @staticmethod
    def _authorize(database: sqlite3.Connection, workspace: UUID, token: str) -> None:
        row = database.execute(
            "SELECT credential FROM workspaces WHERE id = ?", (str(workspace),)
        ).fetchone()
        if (
            not row
            or not token
            or not hmac.compare_digest(
                row["credential"], sha256(token.encode()).hexdigest()
            )
        ):
            raise AgentNotFound

    def register_workspace(self, workspace: UUID, token: str) -> str:
        """Authorize a workspace or issue its initial browser credential."""
        with self._write() as database:
            existing = database.execute(
                "SELECT 1 FROM workspaces WHERE id = ?", (str(workspace),)
            ).fetchone()
            if existing:
                self._authorize(database, workspace, token)
                return token
            credential = secrets.token_urlsafe(32)
            database.execute(
                "INSERT INTO workspaces VALUES (?, ?)",
                (str(workspace), sha256(credential.encode()).hexdigest()),
            )
            return credential

    def workspace(self, token: str) -> dict | None:
        """Return the current browser workspace and its registered character index."""
        if not token:
            return None
        with closing(self._connect()) as database, database:
            database.execute("BEGIN")
            row = database.execute(
                "SELECT id FROM workspaces WHERE credential = ?",
                (sha256(token.encode()).hexdigest(),),
            ).fetchone()
            if not row:
                return None
            workspace_id = UUID(row["id"])
            rows = database.execute(
                "SELECT id, character_id, archived FROM agents WHERE workspace_id = ? ORDER BY rowid",
                (str(workspace_id),),
            ).fetchall()
            return {
                "workspace_id": workspace_id,
                "agents": [
                    self._read_agent(database, workspace_id, row["id"]).public()
                    for row in rows
                    if not row["archived"]
                ],
                "archived_characters": [
                    row["character_id"] for row in rows if row["archived"]
                ],
            }

    @staticmethod
    def _read_agent(
        database: sqlite3.Connection,
        workspace: UUID,
        identifier: str,
        *,
        by_character: bool = False,
    ) -> RegisteredAgent:
        if by_character:
            predicate = "a.character_id = ?"
        else:
            predicate = "a.id = ?"
        row = database.execute(
            "SELECT a.id, a.history_scope, a.memory_imported, p.profile, p.personality "
            "FROM agents a JOIN agent_profiles p ON a.id = p.agent_id AND a.version = p.version "
            f"WHERE a.workspace_id = ? AND a.archived = 0 AND {predicate}",
            (str(workspace), identifier),
        ).fetchone()
        if not row:
            raise AgentNotFound
        return RegisteredAgent(
            row["id"],
            row["history_scope"],
            StudioPersona.model_validate_json(row["profile"], context={"stored": True}),
            PresetProfile.model_validate_json(row["personality"]),
            bool(row["memory_imported"]),
        )

    def get(self, workspace: UUID, token: str, agent_id: str) -> RegisteredAgent:
        """Read one active agent in the authenticated workspace."""
        with closing(self._connect()) as database:
            self._authorize(database, workspace, token)
            return self._read_agent(database, workspace, agent_id)

    def create(
        self,
        profile: StudioPersona,
        token: str,
        *,
        legacy: bool = False,
        source_id: str | None = None,
    ) -> RegisteredAgent:
        """Create an agent once for a browser character, preserving legacy history scopes."""
        workspace = profile.workspace_id
        with self._write() as database:
            self._authorize(database, workspace, token)
            existing = database.execute(
                "SELECT archived FROM agents WHERE workspace_id = ? AND character_id = ?",
                (str(workspace), profile.character_id),
            ).fetchone()
            if existing:
                return self._read_agent(
                    database, workspace, profile.character_id, by_character=True
                )
            agent_id = uuid4().hex
            scope = profile.history_scope if legacy else f"studio-{agent_id}"
            template = studio_presets().get(profile.preset_id or "")
            if source_id:
                source = self._read_agent(database, workspace, source_id)
                personality = source.personality
                profile = source.profile.model_copy(
                    update={
                        "character_id": profile.character_id,
                        "name": profile.name,
                        "memories": [],
                    }
                )
            elif template:
                personality = PresetProfile.model_validate(
                    template.model_dump(exclude={"rules"})
                )
            else:
                traits = dict.fromkeys(BigFive.model_fields, 0.5)
                traits["openness"] = profile.exploration / 100
                personality = PresetProfile(
                    version=1,
                    label=profile.name,
                    role="사용자가 꺼낸 이야기를 함께 나누는 동료",
                    background=profile.description,
                    style=profile.tone or "자연스러운 한국어",
                    values=("정확한 확인", "현재 주제에 맞는 응답", "상대 존중"),
                    traits=BigFive(**traits),
                )
            personality = personality.model_copy(
                update={
                    "version": 1,
                    "label": profile.name,
                    "traits": profile.traits or personality.traits,
                }
            )
            profile = profile.model_copy(update={"traits": personality.traits})
            database.execute(
                "INSERT INTO agents (id, workspace_id, character_id, history_scope, version, memory_imported) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (
                    agent_id,
                    str(workspace),
                    profile.character_id,
                    scope,
                    int(not legacy),
                ),
            )
            self._insert_profile(database, agent_id, profile, personality)
            return RegisteredAgent(agent_id, scope, profile, personality, not legacy)

    @staticmethod
    def _insert_profile(
        database: sqlite3.Connection,
        agent_id: str,
        profile: StudioPersona,
        personality: PresetProfile,
    ) -> None:
        database.execute(
            "INSERT INTO agent_profiles VALUES (?, ?, ?, ?)",
            (
                agent_id,
                personality.version,
                profile.model_dump_json(),
                personality.model_dump_json(),
            ),
        )

    def update(
        self, agent_id: str, token: str, version: int, profile: StudioPersona
    ) -> RegisteredAgent:
        """Persist a new revision atomically when the caller has the current revision."""
        with self._write() as database:
            self._authorize(database, profile.workspace_id, token)
            current = self._read_agent(database, profile.workspace_id, agent_id)
            if (
                current.personality.version != version
                or current.profile.character_id != profile.character_id
                or current.profile.preset_id != profile.preset_id
            ):
                raise ProfileConflict
            profile = profile.model_copy(
                update={"traits": profile.traits or current.personality.traits}
            )
            if current.profile == profile:
                return current
            personality = current.personality.model_copy(
                update={
                    "version": version + 1,
                    "label": profile.name,
                    "traits": profile.traits,
                }
            )
            self._insert_profile(database, agent_id, profile, personality)
            database.execute(
                "UPDATE agents SET version = ? WHERE id = ?", (version + 1, agent_id)
            )
            return RegisteredAgent(
                agent_id,
                current.history_scope,
                profile,
                personality,
                current.memory_imported,
            )

    def archive(self, workspace: UUID, token: str, agent_id: str) -> None:
        """Hide an agent while preserving its existing profile and history."""
        with self._write() as database:
            self._authorize(database, workspace, token)
            self._read_agent(database, workspace, agent_id)
            database.execute("UPDATE agents SET archived = 1 WHERE id = ?", (agent_id,))

    @staticmethod
    def _insert_memory(
        database: sqlite3.Connection, agent_id: str, record: dict
    ) -> None:
        database.execute(
            "INSERT OR IGNORE INTO agent_memories VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                agent_id,
                record["id"],
                record["occurred_at"],
                record["embedding_model"] if record.get("vector") else "",
                record["text"],
                json.dumps(record, ensure_ascii=False),
                record.get("superseded_by"),
            ),
        )

    def import_memories(self, agent: RegisteredAgent) -> None:
        """Copy previously saved conversation memories once for a migrated agent."""
        if agent.memory_imported:
            return
        histories = get_history_list(agent.history_scope)
        with self._write() as database:
            if database.execute(
                "SELECT memory_imported FROM agents WHERE id = ?", (agent.agent_id,)
            ).fetchone()[0]:
                return
            for history in histories:
                records = get_metadata(agent.history_scope, history["uid"]).get(
                    "studio_rag_v1"
                )
                if not isinstance(records, list):
                    continue
                for record in records:
                    if isinstance(record, dict) and all(
                        isinstance(record.get(field), str)
                        for field in (
                            "id",
                            "occurred_at",
                            "embedding_model",
                            "text",
                            "vector",
                        )
                    ):
                        self._insert_memory(
                            database,
                            agent.agent_id,
                            dict(record, source_history_id=history["uid"]),
                        )
            database.execute(
                "UPDATE agents SET memory_imported = 1 WHERE id = ?", (agent.agent_id,)
            )

    def memories(self, agent_id: str, model: str, limit: int) -> list[dict]:
        """Return recent memories only from the bound agent and embedding model."""
        with closing(self._connect()) as database:
            rows = database.execute(
                "SELECT payload, superseded_by FROM agent_memories WHERE agent_id = ? AND embedding_model = ? "
                "ORDER BY occurred_at DESC, rowid DESC LIMIT ?",
                (agent_id, model, limit),
            ).fetchall()
        return [
            dict(json.loads(row["payload"]), superseded_by=row["superseded_by"])
            for row in reversed(rows)
        ]

    def pending_embeddings(self, agent_id: str, limit: int) -> list[tuple[str, str]]:
        """Read active memories awaiting their first vector, oldest first."""
        with closing(self._connect()) as database:
            rows = database.execute(
                "SELECT event_id, text FROM agent_memories WHERE agent_id = ? "
                "AND embedding_model = '' AND superseded_by IS NULL "
                "ORDER BY occurred_at, rowid LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [(row["event_id"], row["text"]) for row in rows]

    @staticmethod
    def _index_pending(
        database: sqlite3.Connection,
        agent_id: str,
        event_id: str,
        model: str,
        vector: str,
    ) -> None:
        row = database.execute(
            "SELECT payload FROM agent_memories WHERE agent_id = ? AND event_id = ? "
            "AND embedding_model = '' AND superseded_by IS NULL",
            (agent_id, event_id),
        ).fetchone()
        if row is None:
            return
        payload = dict(json.loads(row["payload"]), embedding_model=model, vector=vector)
        database.execute(
            "UPDATE agent_memories SET embedding_model = ?, payload = ? WHERE agent_id = ? AND event_id = ?",
            (model, json.dumps(payload, ensure_ascii=False), agent_id, event_id),
        )

    def index_pending(self, agent_id: str, model: str, vectors: dict[str, str]) -> None:
        """Attach recovered vectors without replacing source text or an existing index."""
        with self._write() as database:
            for event_id, vector in vectors.items():
                self._index_pending(database, agent_id, event_id, model, vector)

    def save_memory(
        self, agent_id: str, record: dict, corrected: tuple[str, ...]
    ) -> None:
        """Append an experience and link any replaced facts in the same transaction."""
        with self._write() as database:
            if not database.execute(
                "SELECT 1 FROM agents WHERE id = ? AND archived = 0", (agent_id,)
            ).fetchone():
                return
            model, vector = record["embedding_model"], record.get("vector")
            duplicate = database.execute(
                "SELECT event_id, embedding_model FROM agent_memories WHERE agent_id = ? "
                "AND embedding_model IN ('', ?) AND text = ? AND superseded_by IS NULL "
                "ORDER BY embedding_model DESC, occurred_at DESC LIMIT 1",
                (agent_id, model, record["text"]),
            ).fetchone()
            if duplicate:
                event_id = duplicate["event_id"]
                if vector and not duplicate["embedding_model"]:
                    self._index_pending(database, agent_id, event_id, model, vector)
            else:
                self._insert_memory(database, agent_id, record)
                event_id = record["id"]
            database.executemany(
                "UPDATE agent_memories SET superseded_by = ? WHERE agent_id = ? AND event_id = ? "
                "AND superseded_by IS NULL AND text != ? AND occurred_at <= ?",
                [
                    (
                        event_id,
                        agent_id,
                        old,
                        record["text"],
                        record["occurred_at"],
                    )
                    for old in corrected
                ],
            )
