"""Separate Korean factual-QA and MemOps adjacent probes; no merged benchmark score."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import sys

from benchmark_memory_live import (
    ROOT,
    append_json,
    mem0_context,
    read_jsonl,
    reader_messages,
)

sys.path.insert(0, str(ROOT / "experiments/memory"))
from benchmark_api import BenchmarkAPI  # noqa: E402
from benchmark_data import (  # noqa: E402
    LexicalRetriever,
    documents,
    evidence_metrics,
    load_heard,
    load_memops_adjacent,
    model_document,
    pack_documents,
    select_cases,
)
from open_llm_vtuber.memory.mem0_store import Mem0Store  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=["heard-ko", "memops-adjacent"])
    parser.add_argument("--assets", type=Path, default=ROOT / "tmp/memory-benchmarks")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-category", type=int, default=1)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument(
        "--mem0",
        action="store_true",
        help="Add real Mem0 extraction to live comparison",
    )
    parser.add_argument(
        "--settings", type=Path, default=ROOT / "experiments/memory/gemini.example.json"
    )
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    cases = select_cases(
        load_heard(args.assets)
        if args.dataset == "heard-ko"
        else load_memops_adjacent(args.assets),
        args.per_category,
    )
    methods = ["recent", "lexical"] if args.dataset == "heard-ko" else ["adjacent-full"]
    if args.mem0:
        methods.append("mem0")
    if args.mem0 and not args.generate:
        parser.error("--mem0 requires --generate; it makes real API calls")
    args.output.mkdir(parents=True, exist_ok=True)
    settings = json.loads(args.settings.read_text(encoding="utf-8"))
    spec = {
        "dataset": args.dataset,
        "question_ids": [c.question_id for c in cases],
        "settings": settings,
        "methods": methods,
        "generate": args.generate,
        "judge": "custom reference-based Gemini auxiliary judge; not upstream MemOps judge or official heard baseline",
    }
    run = args.output / "run.json"
    if run.exists() and json.loads(run.read_text(encoding="utf-8")) != spec:
        raise ValueError("Resume settings differ")
    run.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = read_jsonl(args.output / "results.jsonl")
    done = {(r["question_id"], r["method"]) for r in rows}
    api = BenchmarkAPI(settings, args.key_file, args.output) if args.generate else None
    memory = None
    try:
        if args.mem0:
            memory = Mem0Store.local(
                {
                    **settings,
                    "memory_max_tokens": 4096,
                    "memory_instructions": "Preserve original names, dates, speaker identity, corrections and forget requests from the historical records. Distinguish tentative and confirmed facts.",
                },
                api.key,
                args.output / "mem0",
            )
        for i, case in enumerate(cases):
            docs = documents(case)
            index = LexicalRetriever(docs)
            try:
                for method in methods:
                    if (case.question_id, method) in done:
                        continue
                    if method == "mem0":
                        context, _ = mem0_context(case, memory, args.output)
                        context = [
                            model_document(d)
                            for d in pack_documents(
                                [{**d, "session_id": "unavailable"} for d in context]
                            )
                        ]
                        metrics = {
                            "gold_session_recall": None,
                            "all_gold_sessions_found": None,
                        }
                    else:
                        hits = (
                            index.search(case.question, 10)
                            if method == "lexical"
                            else list(reversed(docs))[:10]
                            if method == "recent"
                            else docs
                        )
                        selected = pack_documents(hits)
                        context = [model_document(d) for d in selected]
                        metrics = (
                            evidence_metrics(case, selected)
                            if args.dataset == "heard-ko"
                            else {
                                "gold_session_recall": None,
                                "all_gold_sessions_found": None,
                            }
                        )
                    row = {
                        "question_id": case.question_id,
                        "category": case.category,
                        "method": method,
                        "context": context,
                        "metrics": metrics,
                    }
                    if api:
                        messages = reader_messages(case, context)
                        if args.dataset == "heard-ko":
                            messages.insert(
                                0,
                                {
                                    "role": "system",
                                    "content": "한국어로 답하라. 기록에 근거하고, 정보가 없으면 추측하지 말라.",
                                },
                            )
                        answer, usage = api.chat(
                            messages, f"answer:{case.question_id}:{method}"
                        )
                        prompt = "Assess the response against the reference answer for this memory question. Say yes only if all required facts or state changes are correct; semantic equivalents are allowed. Reject stale values presented as current or invented personal facts. If the reference says the answer is unknown, require appropriate abstention. Answer yes or no only.\nQuestion: {}\nReference: {}\nResponse: {}".format(
                            case.question, case.answer, answer
                        )
                        label, judge_usage = api.chat(
                            [{"role": "user", "content": prompt}],
                            f"judge:{case.question_id}:{method}",
                            max_tokens=32,
                        )
                        if label.strip().lower().rstrip(".") not in {"yes", "no"}:
                            raise ValueError("Nonbinary auxiliary judgment")
                        row.update(
                            hypothesis=answer,
                            auxiliary_correct=label.strip().lower().rstrip(".")
                            == "yes",
                            answer_usage=usage,
                            judge_usage=judge_usage,
                        )
                    append_json(args.output / "results.jsonl", row)
                    rows.append(row)
                print(f"{args.dataset} {i + 1}/{len(cases)}", flush=True)
            finally:
                index.close()
        summary = {
            "dataset": args.dataset,
            "n": len(cases),
            "generated": args.generate,
            "groups": [],
        }
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["method"]].append(row)
        for method, group in grouped.items():
            scored = [r for r in group if "auxiliary_correct" in r]
            recalled = [
                r for r in group if r["metrics"]["gold_session_recall"] is not None
            ]
            summary["groups"].append(
                {
                    "method": method,
                    "rows": len(group),
                    "auxiliary_accuracy": statistics.mean(
                        r["auxiliary_correct"] for r in scored
                    )
                    if scored
                    else None,
                    "mean_evidence_recall": statistics.mean(
                        r["metrics"]["gold_session_recall"] for r in recalled
                    )
                    if recalled
                    else None,
                }
            )
        (args.output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        if memory:
            memory.close()
        if api:
            api.close()


if __name__ == "__main__":
    main()
