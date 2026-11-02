"""Audit official datasets and run resumable LongMemEval retrieval/generation."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/memory"))

from benchmark_data import (  # noqa: E402
    LexicalRetriever,
    documents,
    evidence_metrics,
    load_longmemeval,
    manifest_hash,
    pack_documents,
    select_cases,
)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def audit(assets, output):
    cases = load_longmemeval(assets / "longmemeval_s/longmemeval_s_cleaned.json")
    sample = select_cases(cases)
    stats = {
        "n": len(cases),
        "categories": dict(Counter(c.category for c in cases)),
        "sessions_total": sum(len(c.sessions) for c in cases),
        "turns_total": sum(len(s["turns"]) for c in cases for s in c.sessions),
        "sample": [
            {
                "question_id": c.question_id,
                "category": c.category,
                "sessions": len(c.sessions),
                "retrieval_chunks": len(documents(c)),
            }
            for c in sample
        ],
    }
    heard = [
        json.loads(line)
        for line in (assets / "heard_ko/data/ko_native/test.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    stats["heard_ko"] = {
        "n": len(heard),
        "abilities": dict(Counter(r["ability"] for r in heard)),
        "contains_history": all("history_sessions" in r for r in heard),
    }
    stats["memops_adjacent"] = []
    for path in sorted(
        (
            assets / "memops_adjacent_preview/generated_result/2-evidence_conversation"
        ).glob("*.json")
    ):
        row = json.loads(path.read_text(encoding="utf-8"))
        stats["memops_adjacent"].append(
            {
                "source": path.name,
                "operation": row["operation_type"],
                "turns": sum(
                    len(segment["dialogue"]) for segment in row["conversations"]
                ),
                "questions": sum(
                    q["evaluation_setting"] == "adjacent_operation"
                    for q in row["answer"]
                ),
            }
        )
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "dataset-audit.json", stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def retrieve(args):
    cases = select_cases(
        load_longmemeval(args.assets / "longmemeval_s/longmemeval_s_cleaned.json"),
        args.per_category,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "retrievals.jsonl"
    run = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "longmemeval_s_cleaned",
        "dataset_sha256": manifest_hash(
            args.assets / "longmemeval_s/longmemeval_s_cleaned.json"
        ),
        "selected_ids": [c.question_id for c in cases],
        "per_category": args.per_category,
        "seed": 20261102,
        "methods": args.methods,
        "top_k": args.top_k,
        "char_budget": args.char_budget,
        "chunk_chars": 2400,
        "overlap_chars": 150,
    }
    run_path = args.output / "run.json"
    if run_path.exists():
        prior = json.loads(run_path.read_text(encoding="utf-8"))
        for key in set(run) - {"created_utc"}:
            if run[key] != prior[key]:
                raise ValueError(f"Resume settings differ: {key}")
    else:
        write_json(run_path, run)
    if path.exists():
        with path.open(encoding="utf-8") as file:
            existing = [json.loads(line) for line in file if line.strip()]
    else:
        existing = []
    done = {(r["question_id"], r["method"]) for r in existing}
    with path.open("a", encoding="utf-8") as file:
        for i, case in enumerate(cases):
            docs = documents(case)
            retriever = LexicalRetriever(docs)
            try:
                for method in args.methods:
                    if (case.question_id, method) in done:
                        continue
                    start = time.perf_counter()
                    if method == "lexical":
                        selected = retriever.search(case.question, args.top_k)
                    elif method == "recent":
                        selected = list(reversed(docs))[: args.top_k]
                    else:
                        # Explicit diagnostic upper bound using gold; never a real retriever.
                        selected = [
                            doc
                            for doc in docs
                            if doc["session_id"] in case.evidence_session_ids
                        ]
                    selected = pack_documents(selected, args.char_budget)
                    row = {
                        "question_id": case.question_id,
                        "category": case.category,
                        "method": method,
                        "question": case.question,
                        "question_date": case.question_date,
                        "search_ms": (time.perf_counter() - start) * 1000,
                        "corpus_chunks": len(docs),
                        "selected_chunks": selected,
                        "metrics": evidence_metrics(case, selected),
                    }
                    file.write(json.dumps(row, ensure_ascii=False) + "\n")
                    file.flush()
                    existing.append(row)
            finally:
                retriever.close()
            if i % 25 == 0 or i == len(cases) - 1:
                print(f"Retrieval {i + 1}/{len(cases)}", flush=True)
    grouped = defaultdict(list)
    for row in existing:
        if row["metrics"]["gold_session_recall"] is not None:
            grouped[row["method"]].append(row)
    summary = {
        "dataset_n": len(cases),
        "retrieval_rows": len(existing),
        "metrics": [
            {
                "method": method,
                "answerable_n": len(rows),
                "mean_gold_session_recall_after_budget": statistics.mean(
                    r["metrics"]["gold_session_recall"] for r in rows
                ),
                "all_gold_sessions_found_rate_after_budget": statistics.mean(
                    r["metrics"]["all_gold_sessions_found"] for r in rows
                ),
                "all_gold_turns_hit_rate_after_budget": statistics.mean(
                    r["metrics"]["all_gold_turns_hit"]
                    for r in rows
                    if r["metrics"].get("all_gold_turns_hit") is not None
                ),
                "mean_gold_turn_hit_fraction_after_budget": statistics.mean(
                    r["metrics"]["gold_turn_hit_fraction"]
                    for r in rows
                    if r["metrics"].get("gold_turn_hit_fraction") is not None
                ),
            }
            for method, rows in grouped.items()
        ],
    }
    write_json(args.output / "retrieval-summary.json", summary)
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["audit", "retrieve"])
    parser.add_argument("--assets", type=Path, default=ROOT / "tmp/memory-benchmarks")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--per-category",
        type=int,
        default=1,
        help="0 selects all 500; otherwise fixed stratified subset",
    )
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=["recent", "lexical", "oracle"],
        default=["recent", "lexical"],
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--char-budget", type=int, default=24000)
    args = parser.parse_args()
    if args.per_category < 0 or args.top_k < 1 or args.char_budget < 256:
        parser.error("Invalid sample size, top-k or character budget")
    if args.stage == "audit":
        audit(args.assets, args.output)
    else:
        retrieve(args)


if __name__ == "__main__":
    main()
