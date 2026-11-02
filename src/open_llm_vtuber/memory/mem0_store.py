"""Small adapter around the public mem0ai 2.2.1 SDK, not a memory engine rewrite."""

import importlib.metadata
import os
from pathlib import Path

from .store import MemoryScope


class Mem0Store:
    def __init__(self, sdk):
        self.sdk = sdk

    @classmethod
    def local(cls, settings: dict, api_key: str, directory: Path):
        directory = directory.resolve()
        directory.mkdir(parents=True, exist_ok=True)
        # Set before importing Mem0; keep its auxiliary local stores in the experiment.
        os.environ["MEM0_TELEMETRY"] = "false"
        os.environ["MEM0_DIR"] = str(directory / "sdk")
        version = importlib.metadata.version("mem0ai")
        if version != "2.2.1":
            raise RuntimeError(f"Tested SDK is mem0ai==2.2.1; found {version}")
        from mem0 import Memory

        common = {"api_key": api_key, "openai_base_url": settings["base_url"]}
        config = {
            "llm": {
                "provider": "openai",
                "config": {
                    **common,
                    "model": settings["model"],
                    "temperature": 0,
                    "max_tokens": settings.get("memory_max_tokens", 2048),
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    **common,
                    "model": settings["embedding_model"],
                    "embedding_dims": settings["embedding_dims"],
                },
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "persona_memory",
                    "embedding_model_dims": settings["embedding_dims"],
                    "path": str(directory / "qdrant"),
                    "on_disk": True,
                },
            },
            "history_db_path": str(directory / "mem0_history.db"),
        }
        if settings.get("memory_instructions"):
            config["custom_instructions"] = settings["memory_instructions"]
        return cls(Memory.from_config(config))

    def add(self, scope: MemoryScope, text: str, event_id: str, session_id: str):
        # Only user evidence is admitted here. Generated persona replies are not facts.
        return self.sdk.add(
            [{"role": "user", "content": text}],
            user_id=scope.key,
            metadata={"event_id": event_id, "session_id": session_id},
            infer=True,
        )

    def search(self, scope: MemoryScope, query: str, limit=5):
        if limit < 1:
            raise ValueError("limit must be positive")
        result = self.sdk.search(
            query, filters={"user_id": scope.key}, top_k=limit, threshold=0.1
        )
        return result["results"]

    def forget(self, scope: MemoryScope):
        self.sdk.delete_all(user_id=scope.key)

    def close(self):
        # SDK close() closes the history DB; Qdrant's local lock also needs release.
        self.sdk.close()
        seen = set()
        for name in ("vector_store", "_telemetry_vector_store", "_entity_store"):
            client = getattr(getattr(self.sdk, name, None), "client", None)
            if client is not None and id(client) not in seen:
                client.close()
                seen.add(id(client))
