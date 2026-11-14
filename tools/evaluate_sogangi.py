"""Opt-in persona dialogue evaluation through the real Agent, without ASR/TTS or user history."""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

# Support `python tools/evaluate_sogangi.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def automatic_signals(text, case):
    emotions = re.findall(
        r"\[(neutral|anger|disgust|fear|joy|smirk|sadness|surprise)\]", text, flags=re.I
    )
    text = re.sub(
        r"\[(neutral|anger|disgust|fear|joy|smirk|sadness|surprise)\]",
        "",
        text,
        flags=re.I,
    ).strip()
    signals = {"spoken_text": bool(text.strip())}
    if case.get("allowed_emotions"):
        signals["allowed_emotions"] = all(
            emotion.lower() in case["allowed_emotions"] for emotion in emotions
        )
    if case.get("contains_any"):
        signals["expected_word"] = any(word in text for word in case["contains_any"])
    if case.get("formal_ending"):
        signals["formal_ending"] = bool(re.search(r"(요|니다)[.!?~…\s]*$", text))
    return signals


async def evaluate(args, cases):
    # Do not print configuration, SDK diagnostics or arbitrary provider errors.
    from loguru import logger

    logger.remove()
    from src.open_llm_vtuber.config_manager.utils import read_yaml, validate_config
    from src.open_llm_vtuber.conversations.conversation_utils import create_batch_input
    from src.open_llm_vtuber.live2d_model import Live2dModel
    from src.open_llm_vtuber.service_context import ServiceContext, deep_merge

    raw = read_yaml("conf.yaml")
    raw["character_config"] = deep_merge(
        raw["character_config"],
        read_yaml("characters/ko_sogangi.yaml")["character_config"],
    )
    config = validate_config(raw)
    settings = config.character_config.agent_config.agent_settings.basic_memory_agent
    if (
        config.character_config.agent_config.conversation_agent_choice
        != "basic_memory_agent"
        or settings.use_mcpp
    ):
        raise ValueError(
            "Evaluation requires basic_memory_agent with use_mcpp disabled."
        )
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Synthetic in-session dialogue; no tools, real game actions, ASR/TTS or private history.",
        "human_review_required": True,
        "persona_sha256": hashlib.sha256(
            config.character_config.persona_prompt.encode()
        ).hexdigest(),
        "case_file_sha256": hashlib.sha256(Path(args.cases).read_bytes()).hexdigest(),
        "provider": settings.llm_provider,
        "cases": [],
    }
    provider = getattr(
        config.character_config.agent_config.llm_configs, settings.llm_provider
    )
    report["model"] = getattr(provider, "model", None)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for case in cases:
        started = time.perf_counter()
        context = ServiceContext()
        context.config = config.model_copy(deep=True)
        context.character_config = context.config.character_config
        context.system_config = context.config.system_config
        context.live2d_model = Live2dModel(context.character_config.live2d_model_name)
        item = {
            "id": case["id"],
            "review": case["review"],
            "human_verdict": "pending",
            "turns": [],
        }
        try:
            await context.init_agent(
                context.character_config.agent_config,
                context.character_config.persona_prompt,
            )
            for prompt in case["turns"]:
                started = time.perf_counter()
                batch = create_batch_input(
                    input_text=prompt,
                    images=None,
                    from_name="Synthetic evaluator",
                    metadata={"require_spoken_response": True},
                )
                pieces = []
                async for chunk in context.agent_engine.chat(batch):
                    if hasattr(chunk, "display_text"):
                        pieces.append(chunk.display_text.text)
                text = " ".join(piece.strip() for piece in pieces if piece.strip())
                item["turns"].append(
                    {
                        "input": prompt,
                        "response": text,
                        "seconds": round(time.perf_counter() - started, 3),
                    }
                )
            item["automatic_signals"] = automatic_signals(
                item["turns"][-1]["response"], case
            )
        except Exception as error:
            item["error_type"] = type(error).__name__
            item["error_kind"] = {
                "LLM rate limit exceeded": "rate_limit",
                "LLM connection failed or response timed out": "connection_or_timeout",
                "LLM request failed": "provider_error",
            }.get(str(error), "request_failed")
            item["failed_after_seconds"] = round(time.perf_counter() - started, 3)
            item["automatic_signals"] = {"request_completed": False}
        finally:
            await context.close()
        report["cases"].append(item)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        signals = item["automatic_signals"]
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "signals": signals,
                    "human_verdict": "pending",
                    "error_kind": item.get("error_kind"),
                }
            ),
            flush=True,
        )
        # A failed provider request is not a reason to spend more quota automatically.
        if "error_type" in item:
            break
    report["automatic_signals_passed"] = all(
        all(case["automatic_signals"].values()) for case in report["cases"]
    )
    report["all_cases_executed"] = len(report["cases"]) == len(cases)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report["automatic_signals_passed"] and report["all_cases_executed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Enable real API calls")
    parser.add_argument("--cases", default="tests/persona/sogangi-cases.json")
    parser.add_argument(
        "--case", action="append", dest="selected", help="Select a case id; repeatable"
    )
    parser.add_argument("--max-calls", type=int, default=8)
    parser.add_argument("--output", default="tmp/sogangi-persona/report.json")
    args = parser.parse_args()
    data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = [
        case
        for case in data["cases"]
        if not args.selected or case["id"] in args.selected
    ]
    if not cases or (
        args.selected and set(args.selected) - {case["id"] for case in cases}
    ):
        parser.error("Unknown or empty case selection")
    count = sum(len(case["turns"]) for case in cases)
    if not 1 <= args.max_calls <= 24 or count > args.max_calls:
        parser.error(
            f"Selected cases need {count} calls; max-calls must allow this and be at most 24"
        )
    if not args.live:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "cases": [case["id"] for case in cases],
                    "maximum_calls": count,
                    "api_calls": 0,
                }
            )
        )
        return
    print(
        f"Running {len(cases)} synthetic cases; at most {count} LLM calls. Human review is required.",
        flush=True,
    )
    try:
        passed = asyncio.run(evaluate(args, cases))
    except Exception as error:
        print(
            f"Evaluation stopped: {type(error).__name__}. No provider/configuration details printed.",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
