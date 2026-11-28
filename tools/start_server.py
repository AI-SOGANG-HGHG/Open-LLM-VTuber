"""Start the Linux server with a private .env file, without sourcing shell code."""

import argparse
import os
from pathlib import Path
import shutil
import sys

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check local setup without API calls"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    )

    if not (ROOT / "conf.yaml").is_file():
        print("Copy config_templates/conf.studio.yaml to conf.yaml.", file=sys.stderr)
        return 2

    provider_keys = {"openai_llm": "OPENAI_API_KEY", "gemini_llm": "GEMINI_API_KEY"}
    credentials = dotenv_values(ROOT / ".env", interpolate=False)
    for name in provider_keys.values():
        if credentials.get(name):
            os.environ[name] = credentials[name].strip()

    from loguru import logger
    from src.open_llm_vtuber.logging_utils import secret_redactor
    from src.open_llm_vtuber.config_manager import read_yaml, validate_config

    secret_redactor.add_config(
        {name: os.environ.get(name) for name in provider_keys.values()}
    )
    logger.configure(patcher=secret_redactor)
    raw_config = read_yaml("conf.yaml")
    secret_redactor.add_config(raw_config)
    agent = raw_config.get("character_config", {}).get("agent_config", {})
    if agent.get("conversation_agent_choice") == "basic_memory_agent":
        provider = (
            agent.get("agent_settings", {})
            .get("basic_memory_agent", {})
            .get("llm_provider")
        )
        key_name = provider_keys.get(provider)
        if key_name:
            key = (
                (agent.get("llm_configs", {}).get(provider) or {}).get("llm_api_key")
                or ""
            ).strip()
            if not key or key.startswith(("${", "YOUR_", "Your ")):
                print(
                    f"Set {key_name} in .env and reference it in {provider}.llm_api_key.",
                    file=sys.stderr,
                )
                return 2

    auth_file = ROOT / "private/studio-auth.env"
    if auth_file.is_file():
        settings = dotenv_values(auth_file, interpolate=False)
        for name in (
            "STUDIO_AUTH_ENABLED",
            "STUDIO_AUTH_USERNAME",
            "STUDIO_AUTH_PASSWORD_HASH",
            "STUDIO_PUBLIC_ORIGIN",
        ):
            if settings.get(name):
                os.environ[name] = settings[name]

    if not (ROOT / "frontend/index.html").is_file():
        print("Run git submodule update --init --recursive first.", file=sys.stderr)
        return 2
    if not shutil.which("ffmpeg"):
        print(
            "Install FFmpeg and add it to PATH before starting the server.",
            file=sys.stderr,
        )
        return 2

    if args.check:
        # The check never prints or sends the key and does not initialize engines.
        config = validate_config(raw_config)
        from src.open_llm_vtuber.server import WebSocketServer  # noqa: F401
        from src.open_llm_vtuber.studio_auth import StudioAuth
        import edge_tts  # noqa: F401
        import sherpa_onnx  # noqa: F401
        import onnxruntime  # noqa: F401

        StudioAuth.from_environment()

        print("Local setup checks passed. API access and live audio are not tested.")
        print(f"Server: {config.system_config.host}:{config.system_config.port}")
        return 0

    command = [sys.executable, str(ROOT / "run_server.py")]
    if args.verbose:
        command.append("--verbose")
    os.execv(sys.executable, command)


if __name__ == "__main__":
    raise SystemExit(main())
