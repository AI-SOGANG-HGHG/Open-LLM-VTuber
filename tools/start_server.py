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
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get(
        "PATH", ""
    )

    credentials = dotenv_values(ROOT / ".env", interpolate=False)
    key = (credentials.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")).strip()
    if not key or key in {"YOUR_API_KEY", "YOUR_GEMINI_API_KEY"}:
        print(f"Set GEMINI_API_KEY in {ROOT / '.env'} and save the file.", file=sys.stderr)
        return 2
    os.environ["GEMINI_API_KEY"] = key

    if not (ROOT / "conf.yaml").is_file():
        print("Copy config_templates/conf.gemini.example.yaml to conf.yaml.", file=sys.stderr)
        return 2
    if not (ROOT / "frontend/index.html").is_file():
        print("Run git submodule update --init --recursive first.", file=sys.stderr)
        return 2
    if not shutil.which("ffmpeg"):
        print("Install FFmpeg and add it to PATH before starting the server.", file=sys.stderr)
        return 2

    if args.check:
        # The check never prints or sends the key and does not initialize engines.
        from loguru import logger
        from src.open_llm_vtuber.logging_utils import secret_redactor
        from src.open_llm_vtuber.config_manager import read_yaml, validate_config

        secret_redactor.add_config({"llm_api_key": key})
        logger.configure(patcher=secret_redactor)
        raw_config = read_yaml("conf.yaml")
        secret_redactor.add_config(raw_config)
        config = validate_config(raw_config)
        from src.open_llm_vtuber.server import WebSocketServer  # noqa: F401
        import edge_tts  # noqa: F401
        import sherpa_onnx  # noqa: F401
        import onnxruntime  # noqa: F401

        print("Local setup checks passed. API access and live audio are not tested.")
        print(f"Server: {config.system_config.host}:{config.system_config.port}")
        return 0

    command = [sys.executable, str(ROOT / "run_server.py")]
    if args.verbose:
        command.append("--verbose")
    os.execv(sys.executable, command)


if __name__ == "__main__":
    raise SystemExit(main())
