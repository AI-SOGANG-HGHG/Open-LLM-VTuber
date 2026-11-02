"""Serialized, lazy storage with bounded waits and no growing request queue."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from uuid import uuid4

from loguru import logger

from .mem0_store import Mem0Store
from .store import TranscriptStore


class RuntimeMemory:
    def __init__(self, config, store_factory=None):
        self.config = config
        self._store_factory = store_factory or self._create_store
        self._store = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag")
        self._pending = None
        self._closed = False
        self._forgotten = set()

    def _create_store(self):
        directory = Path(self.config.directory)
        if self.config.backend == "lexical":
            return TranscriptStore(directory / "transcripts.db")
        settings = json.loads(Path(self.config.mem0_settings_file).read_text("utf-8"))
        key = os.environ.get(self.config.api_key_env)
        if not key:
            raise ValueError("Memory API key environment variable is missing")
        store = Mem0Store.local(settings, key, directory)
        # Bound individual SDK requests too. The outer deadline cannot stop a thread.
        for component in (store.sdk.llm, store.sdk.embedding_model):
            component.client = component.client.with_options(timeout=15, max_retries=0)
        return store

    def _invoke(self, operation, args):
        if args[0].key in self._forgotten:
            return None
        if self._store is None:
            self._store = self._store_factory()
        if operation == "search":
            return self._store.search(*args, limit=self.config.top_k)
        scope, text, event_id, session_id = args
        if self.config.backend == "lexical":
            return self._store.append(scope, event_id, session_id, "user", text)
        return self._store.add(scope, text, event_id, session_id)

    async def _call(self, operation, *args):
        if self._closed or (self._pending is not None and not self._pending.done()):
            return None
        future = self._executor.submit(self._invoke, operation, args)
        self._pending = future
        wrapped = asyncio.wrap_future(future)
        # Consume late failures after a timeout/cancellation without logging private text.
        wrapped.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        try:
            return await asyncio.wait_for(
                asyncio.shield(wrapped), self.config.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.warning("RAG {} timed out; continuing without its result", operation)
        except Exception as error:
            logger.warning("RAG {} unavailable ({})", operation, type(error).__name__)
        return None

    async def search(self, scope, query):
        result = await self._call("search", scope, query)
        return result if isinstance(result, list) else []

    async def remember(self, scope, text):
        await self._call("add", scope, text, uuid4().hex, scope.channel_id)

    async def forget(self, scope):
        # Revoke reads immediately, then delete after any in-flight SDK write.
        if scope.key in self._forgotten or self._closed:
            return
        self._forgotten.add(scope.key)
        future = self._executor.submit(self._forget_scope, scope)
        self._pending = future
        wrapped = asyncio.wrap_future(future)
        wrapped.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        try:
            await asyncio.wait_for(asyncio.shield(wrapped), self.config.timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning("RAG deletion is still pending; scope reads are disabled")
        except Exception as error:
            logger.warning("RAG deletion unavailable ({})", type(error).__name__)

    def _forget_scope(self, scope):
        if self._store is None:
            self._store = self._store_factory()
        self._store.forget(scope)

    async def close(self):
        self._closed = True
        # Close on the same worker as SQLite/Qdrant. Never race a timed-out write.
        future = self._executor.submit(self._close_store)
        await asyncio.wrap_future(future)
        self._executor.shutdown(wait=False)

    def _close_store(self):
        if self._store is not None:
            self._store.close()
            self._store = None


_services = {}


def get_runtime_memory(config):
    """One worker per local store; several connections must not open Qdrant twice."""
    key = str(Path(config.directory).resolve())
    signature = config.model_dump_json()
    if key in _services:
        existing_signature, service = _services[key]
        if existing_signature != signature:
            raise ValueError("RAG directory is already in use with different settings")
        return service
    service = RuntimeMemory(config)
    _services[key] = (signature, service)
    return service


async def close_runtime_memories():
    services = [service for _, service in _services.values()]
    _services.clear()
    await asyncio.gather(*(service.close() for service in services))
