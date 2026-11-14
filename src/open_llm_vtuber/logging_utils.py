"""Keep configured credentials out of application log messages and metadata."""

from collections.abc import Mapping
import re


class SecretRedactor:
    def __init__(self):
        self._secrets: set[str] = set()

    def add_config(self, value) -> None:
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        if isinstance(value, Mapping):
            for key, item in value.items():
                sensitive = any(
                    part in str(key).lower()
                    for part in ("api_key", "secret", "password", "token")
                )
                if sensitive and isinstance(item, str) and len(item) >= 4:
                    self._secrets.add(item)
                self.add_config(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.add_config(item)

    def redact(self, value):
        if isinstance(value, Mapping):
            return {key: self.redact(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.redact(item) for item in value]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        text = str(value)
        for secret in sorted(tuple(self._secrets), key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        return re.sub(r"AIza[\w-]{20,}", "[REDACTED]", text)

    def __call__(self, record) -> None:
        record["message"] = self.redact(record["message"])
        record["extra"] = self.redact(record["extra"])


secret_redactor = SecretRedactor()
