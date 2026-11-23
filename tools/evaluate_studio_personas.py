"""Compare registered Studio personas on synthetic dialogue, using isolated history."""

import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from evaluate_sogangi import automatic_signals

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VARIANTS = ("kang-iseo", "sogangi", "kang-iseo-few-shot")
DEFAULT_CASES = Path("tests/persona/kang-iseo-comparison.json")


def profile_for(variant, examples):
    from src.open_llm_vtuber.studio_persona import StudioPersona

    if variant == "sogangi":
        return StudioPersona(
            workspace_id=uuid4(),
            character_id="sogangi",
            name="서강이",
            avatar="sogangi",
            description="공부나 팀 프로젝트가 막힐 때 같이 방법을 찾아줘요.",
            persona="따뜻하고 호기심 많은 동료. 상대의 이야기에 공감하고, 함께할 수 있는 작은 다음 행동을 제안한다.",
            tone="친근한 반말",
            exploration=40,
        )
    instructions = None
    if variant == "kang-iseo-few-shot":
        lines = [
            "아래는 반응과 말투 예시다. 장면과 표현은 지금 이야기의 내용에 맞춰 바꾼다."
        ]
        for example in examples:
            lines.extend(
                [f"상대: {example['user']}", f"강이서: {example['assistant']}"]
            )
        instructions = "\n".join(lines)
    return StudioPersona(
        workspace_id=uuid4(),
        character_id="kang-iseo",
        name="강이서",
        avatar="ivory-crown",
        description="복잡한 고민을 들어주고 다음에 할 일을 차근차근 정리해 줘요.",
        preset_id="kang-iseo",
        persona=instructions,
        exploration=35,
    )


async def run_case(config, registry, case, variant, examples, result):
    from src.open_llm_vtuber.chat_history_manager import create_new_history
    from src.open_llm_vtuber.conversations.conversation_utils import create_batch_input
    from src.open_llm_vtuber.live2d_model import Live2dModel
    from src.open_llm_vtuber.service_context import ServiceContext
    from src.open_llm_vtuber.studio_persona import apply_studio_persona

    profile = profile_for(variant, examples)
    token = registry.register_workspace(profile.workspace_id, "")
    registered = registry.create(profile, token, legacy=True)
    reconnect_before = case.get("reconnect_before")
    context = ServiceContext()
    try:
        for index, text in enumerate(case["turns"]):
            if index == 0 or index == reconnect_before:
                await context.close()
                registered = registry.get(
                    profile.workspace_id, token, registered.agent_id
                )
                context.config = config.model_copy(deep=True)
                context.system_config = context.config.system_config
                context.character_config = context.config.character_config
                context.live2d_model = Live2dModel(
                    context.character_config.live2d_model_name
                )
                await apply_studio_persona(
                    context, registered.profile, registered, registry
                )
                result["prompt_sha256"] = sha256(
                    context.system_prompt.encode()
                ).hexdigest()
                if reconnect_before is not None:
                    context.history_uid = create_new_history(registered.history_scope)

            agent = context.agent_engine
            batch = create_batch_input(
                input_text=text,
                images=None,
                from_name="합성 사용자",
                metadata={"require_spoken_response": True},
            )
            batch.studio_context = "{}"
            turn = None
            if reconnect_before is not None:
                turn = await agent.studio_runtime.prepare(
                    registered.history_scope,
                    context.history_uid,
                    text,
                    recent_messages=agent.recent_studio_messages(limit=4),
                )
                batch.studio_context = turn.context
                batch.studio_rule_prompt = turn.rule_prompt
                batch.studio_use_recent_dialogue = turn.use_recent_dialogue
            parts = [
                chunk.display_text.text.strip()
                async for chunk in agent.chat(batch)
                if hasattr(chunk, "display_text")
            ]
            response = " ".join(filter(None, parts))
            if not response:
                raise RuntimeError("Missing spoken response")

            item = {"input": text, "response": response}
            if turn is not None:
                await agent.studio_runtime.complete_async(turn)
                item.update(
                    reconnected=index == reconnect_before,
                    appraisal=turn.trace["appraisal"],
                    retrieval=turn.trace["retrieval"],
                    memories=turn.trace["memories"],
                )
            result["turns"].append(item)
        result["automatic_signals"] = automatic_signals(response, case)
        if reconnect_before is not None and case.get("contains_any"):
            result["automatic_signals"]["recalled_current_preference"] = any(
                word in memory["text"]
                for memory in result["turns"][-1]["memories"]
                for word in case["contains_any"]
            )
    finally:
        await context.close()


async def evaluate(args, data, cases):
    from dotenv import dotenv_values
    from loguru import logger

    logger.remove()
    if args.env_file and not os.environ.get("GEMINI_API_KEY"):
        key = dotenv_values(args.env_file, interpolate=False).get("GEMINI_API_KEY")
        if key:
            os.environ["GEMINI_API_KEY"] = key

    from src.open_llm_vtuber.config_manager.utils import read_yaml, validate_config
    from src.open_llm_vtuber.studio_registry import StudioRegistry

    config = validate_config(read_yaml(str(args.config)))
    agents = config.character_config.agent_config
    provider_name = agents.agent_settings.basic_memory_agent.llm_provider
    provider = getattr(agents.llm_configs, provider_name)
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": getattr(provider, "model", None),
        "provider": provider_name,
        "temperature": getattr(provider, "temperature", None),
        "case_file_sha256": sha256(args.cases.read_bytes()).hexdigest(),
        "scope": "Voice and tools disabled. Style cases hold retrieval and appraisal off. Reconnect case uses real Studio recall and appraisal with synthetic history.",
        "results": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="studio-persona-evaluation-") as temp:
        root = Path(temp)
        registry = StudioRegistry(root / "studio.sqlite3")
        with patch(
            "src.open_llm_vtuber.chat_history_manager._conf_directory",
            side_effect=lambda scope: root / "history" / scope,
        ):
            for case in cases:
                for variant in args.variant:
                    result = {
                        "case": case["id"],
                        "variant": variant,
                        "review": case["review"],
                        "human_verdict": "pending",
                        "turns": [],
                    }
                    try:
                        await run_case(
                            config, registry, case, variant, data["examples"], result
                        )
                    except Exception as error:
                        result["error_type"] = type(error).__name__
                        result["error_kind"] = {
                            "LLM rate limit exceeded": "rate_limit",
                            "LLM connection failed or response timed out": "connection_or_timeout",
                            "LLM request failed": "provider_error",
                        }.get(str(error), "evaluation_failed")
                    report["results"].append(result)
                    args.output.write_text(
                        json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    if "error_type" in result:
                        print(
                            f"{case['id']} / {variant}: {result['error_kind']}",
                            flush=True,
                        )
                        return False
                    signals = (
                        "signals ok"
                        if all(result["automatic_signals"].values())
                        else "check failed"
                    )
                    print(
                        f"{case['id']} / {variant}: {signals}; human review pending",
                        flush=True,
                    )
    return all(
        all(result["automatic_signals"].values()) for result in report["results"]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Enable real model calls")
    parser.add_argument("--config", type=Path, default=Path("conf.yaml"))
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Read GEMINI_API_KEY if it is absent from the environment",
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", dest="selected")
    parser.add_argument("--variant", action="append", choices=VARIANTS)
    parser.add_argument(
        "--output", type=Path, default=Path("tmp/kang-iseo-persona/baseline.json")
    )
    args = parser.parse_args()
    args.variant = args.variant or list(VARIANTS[:2])
    data = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = [
        case
        for case in data["cases"]
        if not args.selected or case["id"] in args.selected
    ]
    if not cases or set(args.selected or ()) - {case["id"] for case in cases}:
        parser.error("Unknown or empty case selection")
    turns = sum(len(case["turns"]) for case in cases) * len(args.variant)
    print(f"{len(cases)} scenarios, {turns} text turns; live={args.live}", flush=True)
    if not args.live:
        return
    try:
        completed = asyncio.run(evaluate(args, data, cases))
    except Exception as error:
        sys.exit(
            f"Evaluation stopped: {type(error).__name__}. No provider details printed."
        )
    sys.exit(0 if completed else 1)


if __name__ == "__main__":
    main()
