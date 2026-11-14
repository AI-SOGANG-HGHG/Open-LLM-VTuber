import io
import unittest

from loguru import logger

from src.open_llm_vtuber.logging_utils import SecretRedactor


class LogRedactionTests(unittest.TestCase):
    def test_credentials_are_removed_from_formatted_messages_and_nested_metadata(self):
        redactor = SecretRedactor()
        key = "test-only-provider-key-934"
        token = "test-only-access-token-158"
        redactor.add_config(
            {
                "llm_configs": {"provider": {"llm_api_key": key}},
                "tools": [{"access_token": token}],
            }
        )
        output = io.StringIO()
        isolated_logger = logger.bind().patch(redactor)
        sink = isolated_logger.add(
            output,
            format="{message} {extra}",
            filter=lambda record: record["extra"].get("redaction_test"),
        )
        try:
            isolated_logger.bind(
                redaction_test=True, nested={"value": [key, token]}
            ).info("request failed: {} / {}", key, token)
        finally:
            isolated_logger.remove(sink)
        actual = output.getvalue()
        self.assertNotIn(key, actual)
        self.assertNotIn(token, actual)
        self.assertIn("[REDACTED]", actual)
        self.assertIn("request failed", actual)

    def test_model_names_and_numeric_token_limits_remain_useful(self):
        redactor = SecretRedactor()
        redactor.add_config({"model": "test-model", "max_tokens": 1024})
        self.assertEqual(
            redactor.redact({"model": "test-model", "max_tokens": 1024}),
            {"model": "test-model", "max_tokens": 1024},
        )
