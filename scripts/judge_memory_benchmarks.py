"""Calibrate an independent auxiliary judge and re-score frozen hypotheses."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics

from benchmark_memory_live import ROOT, append_json, read_jsonl
from benchmark_api import BenchmarkAPI
from benchmark_data import load_heard, load_longmemeval, load_memops_adjacent
from longmemeval_official import get_anscheck_prompt


def controls():
    specs = [
        (
            "single-session-user",
            "What is my favorite tea?",
            "barley tea",
            "Barley tea.",
            "Coffee.",
        ),
        (
            "single-session-assistant",
            "What discount did you suggest?",
            "15%",
            "15%",
            "30%",
        ),
        (
            "multi-session",
            "Where do Alice and Bob live?",
            "Alice lives in Seoul and Bob lives in Busan",
            "Alice: Seoul. Bob: Busan.",
            "Alice lives in Seoul.",
        ),
        (
            "knowledge-update",
            "When is the current meeting?",
            "Saturday at 15:00",
            "It was Friday, but now it is Saturday at 15:00.",
            "Friday at 19:00.",
        ),
        (
            "temporal-reasoning",
            "How many days elapsed?",
            "18 days",
            "19 days",
            "30 days",
        ),
        (
            "single-session-preference",
            "What meal would suit me?",
            "The user is vegetarian; suggest a vegetarian meal.",
            "A lentil and vegetable soup would suit you.",
            "A beef steak would suit you.",
        ),
        (
            "abstention",
            "What is my cat's name?",
            "The history never mentions the cat's name.",
            "I do not know; the history does not say.",
            "Your cat's name is Dubu.",
        ),
        (
            "abstention",
            "내 고양이 이름은?",
            "모른다.",
            "기록에 관련 정보가 없어 답변할 수 없습니다.",
            "네 고양이 이름은 두부야.",
        ),
    ]
    return [
        {
            "id": f"control-{i}-{label}",
            "task": task,
            "question": question,
            "answer": answer,
            "response": response,
            "expected": label,
        }
        for i, (task, question, answer, yes, no) in enumerate(specs)
        for label, response in [(True, yes), (False, no)]
    ]


def binary_response(api, prompt, tag):
    text, record = api.chat([{"role": "user", "content": prompt}], tag, max_tokens=1024)
    normalized = text.strip().lower().rstrip(".")
    if normalized not in {"yes", "no"}:
        raise ValueError("Judge returned a nonbinary response")
    return normalized == "yes", text, record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=ROOT / "tmp/memory-benchmarks")
    parser.add_argument(
        "--settings",
        type=Path,
        default=ROOT / "experiments/memory/gemini-judge.example.json",
    )
    parser.add_argument("--key-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    settings = json.loads(args.settings.read_text(encoding="utf-8"))
    settings_path = args.output / "judge-settings.json"
    if settings_path.exists() and json.loads(settings_path.read_text()) != settings:
        raise ValueError("Judge settings changed")
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    api = BenchmarkAPI(settings, args.key_file, args.output)
    try:
        path = args.output / "controls.jsonl"
        results = read_jsonl(path)
        done = {r["id"] for r in results}
        for item in controls():
            if item["id"] in done:
                continue
            prompt = get_anscheck_prompt(
                item["task"],
                item["question"],
                item["answer"],
                item["response"],
                abstention=item["task"] == "abstention",
            )
            label, text, record = binary_response(api, prompt, item["id"])
            row = {**item, "label": label, "judge_response": text, "api_record": record}
            append_json(path, row)
            results.append(row)
            print(f"Control {len(results)}/16: {label == item['expected']}", flush=True)
        passed = sum(r["label"] == r["expected"] for r in results)
        control_summary = {
            "model": settings["model"],
            "correct": passed,
            "n": len(results),
            "all_passed": passed == len(results) == 16,
            "note": "Passing controls does not establish benchmark judge reliability.",
        }
        (args.output / "control-summary.json").write_text(
            json.dumps(control_summary, indent=2), encoding="utf-8"
        )
        if not control_summary["all_passed"]:
            raise SystemExit("Judge failed controls; re-scoring was not started")
        references = None
        for run in args.runs:
            spec = json.loads((run / "run.json").read_text(encoding="utf-8"))
            is_longmemeval = "identity" in spec
            dataset = "longmemeval-s" if is_longmemeval else spec["dataset"]
            if is_longmemeval:
                if references is None:
                    references = {
                        c.question_id: c
                        for c in load_longmemeval(
                            args.assets / "longmemeval_s/longmemeval_s_cleaned.json"
                        )
                    }
                ref_map = references
            else:
                ref_map = {
                    c.question_id: c
                    for c in (
                        load_heard(args.assets)
                        if dataset == "heard-ko"
                        else load_memops_adjacent(args.assets)
                    )
                }
            hypotheses = read_jsonl(
                run / ("responses.jsonl" if is_longmemeval else "results.jsonl")
            )
            dest = args.output / (run.name + ".jsonl")
            judgments = read_jsonl(dest)
            done = {(r["question_id"], r["method"]) for r in judgments}
            for row in hypotheses:
                key = (row["question_id"], row["method"])
                if key in done:
                    continue
                case = ref_map[row["question_id"]]
                if is_longmemeval:
                    prompt = get_anscheck_prompt(
                        case.category,
                        case.question,
                        case.answer,
                        row["hypothesis"],
                        abstention=case.category == "abstention",
                    )
                else:
                    prompt = "Assess this memory answer against the reference. Accept semantic equivalents and appropriate abstention when the reference is unknown. Reject incomplete required facts or stale values stated as current. Reply yes or no only.\nQuestion: {}\nReference: {}\nResponse: {}".format(
                        case.question, case.answer, row["hypothesis"]
                    )
                label, text, record = binary_response(
                    api,
                    prompt,
                    f"rescore:{run.name}:{row['question_id']}:{row['method']}",
                )
                result = {
                    "dataset": dataset,
                    "question_id": case.question_id,
                    "category": case.category,
                    "method": row["method"],
                    "label": label,
                    "judge_response": text,
                    "api_record": record,
                }
                append_json(dest, result)
                judgments.append(result)
                print(
                    f"Rescored {run.name} {len(judgments)}/{len(hypotheses)}",
                    flush=True,
                )
            groups = defaultdict(list)
            for row in judgments:
                groups[row["method"]].append(row["label"])
            summary = {
                "dataset": dataset,
                "hypotheses_source": str(run.resolve()),
                "judge_model": settings["model"],
                "score_class": "upstream-default-model with local runner"
                if settings["model"] == "gpt-4o-2024-08-06"
                and settings["base_url"].rstrip("/") == "https://api.openai.com/v1"
                else "alternative-model auxiliary score",
                "groups": [
                    {
                        "method": method,
                        "n": len(labels),
                        "correct": sum(labels),
                        "accuracy": statistics.mean(labels),
                    }
                    for method, labels in groups.items()
                ],
            }
            (args.output / (run.name + ".summary.json")).write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
    finally:
        api.close()


if __name__ == "__main__":
    main()
