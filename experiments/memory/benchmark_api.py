"""Paced, recorded API calls. No credential or exception text is serialized."""

import json
import os
from pathlib import Path
import time


def quota_diagnostics(exc):
    result = {"daily_exhausted": False, "violations": []}

    def walk(obj):
        if isinstance(obj, dict):
            for item in obj.get("violations", []):
                safe = {
                    key: item[key]
                    for key in ("quotaMetric", "quotaId", "quotaValue")
                    if key in item
                }
                result["violations"].append(safe)
                if "perday" in item.get("quotaId", "").lower():
                    result["daily_exhausted"] = True
            if "retryDelay" in obj:
                result["retry_delay"] = obj["retryDelay"]
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(getattr(exc, "body", None))
    return result


class BenchmarkAPI:
    def __init__(self, settings, key_file, output: Path, interval=5):
        self.settings = settings
        self.key = os.getenv(settings["api_key_env"], "").strip()
        if not self.key and key_file:
            self.key = key_file.read_text(encoding="utf-8").strip()
        if not self.key:
            raise ValueError(f"Missing credential: set {settings['api_key_env']}")
        from openai import OpenAI

        self.client = OpenAI(
            api_key=self.key, base_url=settings["base_url"], timeout=60, max_retries=0
        )
        self.log = output / "api-usage.jsonl"
        self.interval = interval
        self.last_call = 0

    def chat(self, messages, tag, max_tokens=512, temperature=0):
        for attempt in range(3):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            start = time.perf_counter()
            record = {
                "tag": tag,
                "attempt": attempt + 1,
                "model": self.settings["model"],
            }
            try:
                kwargs = {
                    "model": self.settings["model"],
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if self.settings.get("reasoning_effort"):
                    kwargs["reasoning_effort"] = self.settings["reasoning_effort"]
                result = self.client.chat.completions.create(**kwargs)
                record.update(
                    status="ok",
                    response_model=result.model,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    usage=result.usage.model_dump() if result.usage else None,
                )
                self.record(record)
                text = result.choices[0].message.content or ""
                if result.choices[0].finish_reason != "stop" or not text.strip():
                    raise ValueError("Empty or truncated completion")
                return text, record
            except Exception as exc:
                quota = quota_diagnostics(exc)
                self.record(
                    {
                        **record,
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "quota": quota,
                    }
                )
                if (
                    quota["daily_exhausted"]
                    or type(exc).__name__
                    not in {
                        "RateLimitError",
                        "APIConnectionError",
                        "APITimeoutError",
                        "InternalServerError",
                    }
                    or attempt == 2
                ):
                    raise RuntimeError(
                        f"Benchmark API call failed: {type(exc).__name__}"
                    ) from None
                time.sleep(15 * (attempt + 1))

    def record(self, record):
        with self.log.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def close(self):
        self.client.close()
