"""Retry only failed synthetic pilot responses, preserving successes and prompts."""

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

from evaluate_memory import CASES, answer_metrics, summarize_rows, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()
    if args.interval < 0:
        parser.error("interval must be >= 0")
    summary = json.loads((args.output / "summary.json").read_text(encoding="utf-8"))
    settings = summary["settings"]
    key = os.environ.get(settings["api_key_env"], "").strip()
    if not key and args.key_file:
        key = args.key_file.read_text(encoding="utf-8").strip()
    if not key:
        parser.error("API key is required")
    from openai import OpenAI

    path = args.output / "responses.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    failures = [row for row in rows if "error_type" in row]
    cases = {case.id: case for case in CASES}
    if any(row["case"] not in cases for row in rows):
        parser.error("Scenario changed; retry using the original scenario version")
    summary.setdefault("retry_runs", []).append(
        {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "failed_samples_before": len(failures),
        }
    )
    # Preserve the complete original attempt; never overwrite it on later retries.
    original = args.output / "responses.initial.jsonl"
    if not original.exists():
        original.write_bytes(path.read_bytes())
    with OpenAI(
        api_key=key, base_url=settings["base_url"], timeout=45, max_retries=1
    ) as client:
        for i, row in enumerate(failures):
            time.sleep(args.interval)
            row.setdefault("previous_errors", []).append(row["error_type"])
            start = time.perf_counter()
            try:
                result = client.chat.completions.create(
                    model=settings["model"],
                    temperature=0.3,
                    max_tokens=384,
                    messages=row["messages"],
                )
                text = result.choices[0].message.content or ""
                row.update(
                    answer=text,
                    finish_reason=result.choices[0].finish_reason,
                    generation_ms=(time.perf_counter() - start) * 1000,
                    usage=result.usage.model_dump() if result.usage else None,
                    metrics=answer_metrics(text, cases[row["case"]]),
                )
                row.pop("error_type")
            except Exception as exc:
                row["error_type"] = type(exc).__name__
            partial = path.with_suffix(".partial")
            partial.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
                encoding="utf-8",
            )
            partial.replace(path)
            print(
                f"Retry {i + 1}/{len(failures)}: {row.get('error_type', 'ok')}",
                flush=True,
            )
    summary.update(summarize_rows(rows))
    write_json(args.output / "summary.json", summary)
    with (args.output / "blind-review.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "sample_id",
                "question",
                "answer",
                "factual_0_2",
                "grounded_0_2",
                "warmth_1_5",
                "playfulness_1_5",
                "formality_1_5",
                "notes",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["sample_id"],
                    cases[row["case"]].question,
                    row.get("answer", ""),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    if summary["generation_errors"]:
        raise SystemExit(f"Still failed: {summary['generation_errors']}")


if __name__ == "__main__":
    main()
