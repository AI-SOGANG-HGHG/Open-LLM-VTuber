"""Replay synthetic chat: recent context vs SQLite lexical RAG vs public Mem0."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "memory"))

from scenario import BASE_SYSTEM, CASES, PERSONAS, SCOPE, admit, events  # noqa: E402
from open_llm_vtuber.memory.mem0_store import Mem0Store  # noqa: E402
from open_llm_vtuber.memory.store import TranscriptStore  # noqa: E402


def packed_context(recent, hits, budget=4000):
    """Budget serialized evidence in characters (not model tokens)."""
    context = {"recent": [], "memories": []}
    for key, items in (("memories", hits), ("recent", list(reversed(recent)))):
        for item in items:
            context[key].append(item)
            if len(json.dumps(context, ensure_ascii=False)) > budget:
                context[key].pop()
    context["recent"].reverse()
    return context


def answer_metrics(text, case):
    normalized = text.replace(" ", "").lower()
    return {
        "answer_chars": len(text),
        "required_groups_matched": sum(
            any(alias.replace(" ", "").lower() in normalized for alias in group)
            for group in case.required
        ),
        "required_groups_total": len(case.required),
        "forbidden_term_found": any(term in text for term in case.forbidden),
        "polite_endings": sum(text.count(end) for end in ("요.", "니다.", "까요?")),
        "empathy_markers": sum(
            text.count(word) for word in ("마음", "괜찮", "힘들", "걱정", "이해")
        ),
        "exclamations": text.count("!"),
    }


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize_rows(rows):
    groups = []
    for mode in sorted({row["mode"] for row in rows}):
        for persona in PERSONAS:
            group = [
                r
                for r in rows
                if r["mode"] == mode and r["persona"] == persona and "metrics" in r
            ]
            if group:
                groups.append(
                    {
                        "mode": mode,
                        "persona": persona,
                        "n": len(group),
                        "required_keyword_group_recall": sum(
                            r["metrics"]["required_groups_matched"] for r in group
                        )
                        / sum(r["metrics"]["required_groups_total"] for r in group),
                        "mean_answer_chars": statistics.mean(
                            r["metrics"]["answer_chars"] for r in group
                        ),
                        "forbidden_term_samples": sum(
                            r["metrics"]["forbidden_term_found"] for r in group
                        ),
                    }
                )
    return {
        "generation_errors": sum("error_type" in row for row in rows),
        "samples": len(rows),
        "groups": groups,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["lexical", "mem0"], default="lexical")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Make real model calls; otherwise record prompts only",
    )
    parser.add_argument(
        "--settings", type=Path, default=ROOT / "experiments/memory/gemini.example.json"
    )
    parser.add_argument(
        "--key-file", type=Path, help="Optional local key file, never copied to results"
    )
    parser.add_argument("--noise", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--request-interval",
        type=float,
        default=5,
        help="Pause between generation requests",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="A NEW directory, preferably under tmp/",
    )
    args = parser.parse_args()
    if args.noise < 8 or args.repeats < 1 or args.request_interval < 0:
        parser.error("noise >= 8, repeats >= 1, request-interval >= 0 required")
    args.output.mkdir(parents=True, exist_ok=False)
    settings = json.loads(args.settings.read_text(encoding="utf-8"))
    key = ""
    client = None
    if args.backend == "mem0" or args.generate:
        key = os.environ.get(settings["api_key_env"], "").strip()
        if not key and args.key_file:
            key = args.key_file.read_text(encoding="utf-8").strip()
        if not key:
            parser.error(
                "Set the configured API key environment variable or --key-file"
            )
        from openai import OpenAI

        client = OpenAI(
            api_key=key, base_url=settings["base_url"], timeout=45, max_retries=1
        )
    store = TranscriptStore(args.output / "transcripts.db")
    mem0 = None
    rows = []
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "backend": args.backend,
        "generated": args.generate,
        "noise_events": args.noise,
        "repeats": args.repeats,
        "settings": settings,
        "context_char_budget": 4000,
        "top_k": 5,
        "metrics_caution": "Keyword and style counts are heuristics, not judged correctness/personality scores. A single repeat is a pilot.",
    }
    try:
        if args.backend == "mem0":
            summary["mem0ai_version"] = importlib.metadata.version("mem0ai")
            mem0 = Mem0Store.local(settings, key, args.output / "mem0")
        seen = set()
        admitted = total = 0
        ingest_start = time.perf_counter()
        add_results = []
        corpus_hash = hashlib.sha256()
        for event_id, session_id, scope, role, content in events(args.noise):
            total += 1
            corpus_hash.update(
                json.dumps(
                    [event_id, session_id, scope.values(), role, content],
                    ensure_ascii=False,
                ).encode()
            )
            store.append(scope, event_id, session_id, role, content)
            if mem0 and admit(role, content, seen, scope):
                admitted += 1
                result = mem0.add(scope, content, event_id, session_id)
                add_results.append({"event_id": event_id, "result": result})
                print(f"Mem0 ingest {admitted}: {event_id}", flush=True)
        summary.update(
            total_events=total,
            mem0_admitted_events=admitted,
            ingestion_seconds=time.perf_counter() - ingest_start,
            corpus_sha256=corpus_hash.hexdigest(),
        )
        write_json(args.output / "ingestion.json", add_results)
        if mem0:
            # Reopen on-disk Qdrant and SQLite before querying to check persistence.
            mem0.close()
            mem0 = Mem0Store.local(settings, key, args.output / "mem0")
            summary["reopened_mem0_before_search"] = True
        recent = [
            {"role": r["role"], "text": r["content"]} for r in store.recent(SCOPE)
        ]
        modes = ["recent", "lexical"] + (["mem0"] if mem0 else [])
        jobs = []
        retrievals = []
        for case in CASES:
            for mode in modes:
                start = time.perf_counter()
                if mode == "mem0":
                    hits = [
                        {"id": r["id"], "text": r["memory"], "score": r.get("score")}
                        for r in mem0.search(SCOPE, case.question)
                    ]
                elif mode == "lexical":
                    hits = [
                        {"id": r["event_id"], "text": r["content"]}
                        for r in store.search(SCOPE, case.question)
                    ]
                else:
                    hits = []
                elapsed = (time.perf_counter() - start) * 1000
                context = packed_context(recent, hits)
                retrievals.append(
                    {
                        "case": case.id,
                        "mode": mode,
                        "search_ms": elapsed,
                        "context": context,
                    }
                )
                for repeat in range(args.repeats):
                    for persona, instruction in PERSONAS.items():
                        messages = [
                            {
                                "role": "system",
                                "content": BASE_SYSTEM + "\n" + instruction,
                            },
                            {
                                "role": "user",
                                "content": json.dumps(
                                    {
                                        "untrusted_context": context,
                                        "question": case.question,
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        ]
                        jobs.append((case, mode, repeat, persona, messages))
        write_json(args.output / "retrievals.json", retrievals)
        # Fixed order randomization avoids putting every persona/mode in one time block.
        random.Random(20261102).shuffle(jobs)
        with (args.output / "responses.jsonl").open("w", encoding="utf-8") as output:
            for i, (case, mode, repeat, persona, messages) in enumerate(jobs):
                row = {
                    "sample_id": f"sample-{i + 1:03}",
                    "case": case.id,
                    "mode": mode,
                    "repeat": repeat,
                    "persona": persona,
                    "messages": messages,
                }
                if args.generate:
                    if i:
                        time.sleep(args.request_interval)
                    start = time.perf_counter()
                    try:
                        response = client.chat.completions.create(
                            model=settings["model"],
                            temperature=0.3,
                            max_tokens=384,
                            messages=messages,
                        )
                        text = response.choices[0].message.content or ""
                        row.update(
                            answer=text,
                            finish_reason=response.choices[0].finish_reason,
                            generation_ms=(time.perf_counter() - start) * 1000,
                            usage=response.usage.model_dump()
                            if response.usage
                            else None,
                            metrics=answer_metrics(text, case),
                        )
                    except Exception as exc:
                        # Do not serialize exceptions: SDK errors can contain request data.
                        row["error_type"] = type(exc).__name__
                    print(
                        f"Generation {i + 1}/{len(jobs)}: {row.get('error_type', 'ok')}",
                        flush=True,
                    )
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                output.flush()
                rows.append(row)
        summary.update(summarize_rows(rows))
        errors = summary["generation_errors"]
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
            questions = {case.id: case.question for case in CASES}
            for row in rows:
                writer.writerow(
                    [
                        row["sample_id"],
                        questions[row["case"]],
                        row.get("answer", ""),
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                    ]
                )
        print(f"Results: {args.output.resolve()}", flush=True)
        if errors:
            raise SystemExit(f"{errors} generation failures; partial results saved")
    finally:
        store.close()
        if mem0:
            mem0.close()
        if client:
            client.close()


if __name__ == "__main__":
    main()
