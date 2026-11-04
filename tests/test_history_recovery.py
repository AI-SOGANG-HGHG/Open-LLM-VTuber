"""A failed restore/write must preserve the existing conversation."""

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from src.open_llm_vtuber import chat_history_manager as history
from src.open_llm_vtuber.websocket_handler import WebSocketHandler


class HistoryFileTests(unittest.TestCase):
    def setUp(self):
        self.previous = Path.cwd()
        self.temporary = tempfile.TemporaryDirectory()
        os.chdir(self.temporary.name)

    def tearDown(self):
        os.chdir(self.previous)
        self.temporary.cleanup()

    def test_unsafe_components_are_rejected_instead_of_reinterpreted(self):
        for value in [
            "..",
            ".",
            "../outside",
            "a/b",
            "a\\b",
            "C:escape",
            "NUL",
            "CON.txt",
            "LPT1",
            "bad\x00name",
            "trailing.",
            " leading",
        ]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    history._get_safe_history_path("character", value)
                with self.assertRaises(ValueError):
                    history._get_safe_history_path(value, "record")
        uid = history.create_new_history("서강이-테스트")
        self.assertTrue(
            Path(history._get_safe_history_path("서강이-테스트", uid)).exists()
        )

    def test_failed_atomic_replace_keeps_previous_record_and_cleans_temporary(self):
        uid = history.create_new_history("test")
        history.store_message("test", uid, "human", "첫 문장")
        before = Path(history._get_safe_history_path("test", uid)).read_bytes()
        with patch.object(
            history.os, "replace", side_effect=OSError("synthetic disk failure")
        ):
            with self.assertRaises(OSError):
                history.store_message("test", uid, "ai", "저장 실패")
        self.assertEqual(
            Path(history._get_safe_history_path("test", uid)).read_bytes(), before
        )
        self.assertEqual(list(Path("chat_history/test").glob("*.tmp")), [])

    def test_corrupt_record_cannot_be_silently_overwritten(self):
        uid = history.create_new_history("test")
        path = Path(history._get_safe_history_path("test", uid))
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            history.store_message("test", uid, "human", "새 문장")
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
        with self.assertRaises(ValueError):
            history.get_history("test", uid, strict=True)
        with self.assertRaises(FileNotFoundError):
            history.get_history("test", "missing", strict=True)
        self.assertEqual(history.get_history("test", "missing"), [])


class HistoryProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = SimpleNamespace(
            character_config=SimpleNamespace(conf_uid="test"),
            history_uid="original",
            agent_engine=Mock(),
        )
        self.handler = WebSocketHandler(SimpleNamespace())
        self.handler.client_contexts["client"] = self.context
        self.socket = SimpleNamespace(send_text=AsyncMock())

    async def test_missing_restore_cannot_reset_current_memory_or_identifier(self):
        with patch(
            "src.open_llm_vtuber.websocket_handler.get_history",
            side_effect=FileNotFoundError,
        ):
            await self.handler._handle_fetch_history(
                self.socket, "client", {"history_uid": "missing"}
            )
        self.context.agent_engine.set_memory_from_history.assert_not_called()
        self.assertEqual(self.context.history_uid, "original")
        self.assertEqual(
            json.loads(self.socket.send_text.call_args.args[0])["type"], "history-error"
        )

    async def test_successful_restore_acknowledges_the_actual_identifier(self):
        with patch(
            "src.open_llm_vtuber.websocket_handler.get_history",
            return_value=[{"role": "human", "content": "試験"}],
        ):
            await self.handler._handle_fetch_history(
                self.socket, "client", {"history_uid": "saved"}
            )
        self.assertEqual(self.context.history_uid, "saved")
        self.assertEqual(
            json.loads(self.socket.send_text.call_args.args[0])["history_uid"], "saved"
        )

    async def test_create_success_and_failure_have_distinct_acknowledgments(self):
        for uid, expected in [
            ("created", "new-history-created"),
            ("", "history-error"),
        ]:
            self.socket.send_text.reset_mock()
            with patch(
                "src.open_llm_vtuber.websocket_handler.create_new_history",
                return_value=uid,
            ):
                await self.handler._handle_create_history(self.socket, "client", {})
            self.socket.send_text.assert_awaited_once()
            self.assertEqual(
                json.loads(self.socket.send_text.call_args.args[0])["type"], expected
            )
