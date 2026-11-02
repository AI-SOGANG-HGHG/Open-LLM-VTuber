"""Local transcript baseline and explicit memory ownership for replay experiments."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata


@dataclass(frozen=True)
class MemoryScope:
    user_id: str
    character_id: str
    channel_id: str

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() for v in self.values()):
            raise ValueError("user_id, character_id and channel_id must be explicit")

    def values(self):
        return self.user_id, self.character_id, self.channel_id

    @property
    def key(self) -> str:
        # One composite ID also avoids SDK-specific AND/OR semantics of entity IDs.
        payload = json.dumps(self.values(), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def lexical_tokens(text: str) -> list[str]:
    """Words and Hangul bigrams; a Korean baseline, not semantic tokenization."""
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).lower())
    tokens = set(words)
    for word in words:
        if any("가" <= char <= "힣" for char in word):
            tokens.update(word[i : i + 2] for i in range(len(word) - 1))
    return sorted(tokens)


class TranscriptStore:
    """Append rows instead of rewriting a JSON array. One connection per caller."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
                scope TEXT NOT NULL, session_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_scope ON events(scope, seq);
            CREATE VIRTUAL TABLE IF NOT EXISTS event_fts USING fts5(tokens);
        """)

    def append(self, scope, event_id, session_id, role, content):
        if role not in {"user", "assistant"} or not content.strip():
            raise ValueError("Expected nonempty user/assistant text")
        row = (event_id, scope.key, session_id, role, content)
        with self.db:
            old = self.db.execute(
                "SELECT event_id,scope,session_id,role,content FROM events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if old:
                if tuple(old) != row:
                    raise ValueError("event_id already has different content or scope")
                return
            cursor = self.db.execute(
                "INSERT INTO events(event_id,scope,session_id,role,content) VALUES(?,?,?,?,?)",
                row,
            )
            if role == "user":
                self.db.execute(
                    "INSERT INTO event_fts(rowid,tokens) VALUES(?,?)",
                    (cursor.lastrowid, " ".join(lexical_tokens(content))),
                )

    def recent(self, scope, limit=8):
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = self.db.execute(
            "SELECT * FROM events WHERE scope=? ORDER BY seq DESC LIMIT ?",
            (scope.key, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def search(self, scope, query, limit=5):
        if limit < 1:
            raise ValueError("limit must be positive")
        tokens = lexical_tokens(query)[:128]
        if not tokens:
            return []
        expression = " OR ".join('"' + word + '"' for word in tokens)
        rows = self.db.execute(
            """SELECT e.*, bm25(event_fts) AS rank FROM event_fts
               JOIN events e ON e.seq=event_fts.rowid
               WHERE event_fts MATCH ? AND e.scope=?
               ORDER BY rank, e.seq DESC LIMIT ?""",
            (expression, scope.key, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def forget(self, scope):
        with self.db:
            self.db.execute(
                "DELETE FROM event_fts WHERE rowid IN (SELECT seq FROM events WHERE scope=?)",
                (scope.key,),
            )
            self.db.execute("DELETE FROM events WHERE scope=?", (scope.key,))

    def close(self):
        self.db.close()
