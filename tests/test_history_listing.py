import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.open_llm_vtuber.chat_history_manager import get_history_list


class HistoryListingTests(unittest.TestCase):
    def test_listing_cannot_delete_empty_histories_still_used_by_open_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory, "first.json")
            second = Path(directory, "second.json")
            first.write_text(json.dumps([{"role": "metadata"}]), encoding="utf-8")
            second.write_text(json.dumps([{"role": "metadata"}]), encoding="utf-8")
            with patch(
                "src.open_llm_vtuber.chat_history_manager._ensure_conf_dir",
                return_value=directory,
            ):
                self.assertEqual(get_history_list("test-character"), [])
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
