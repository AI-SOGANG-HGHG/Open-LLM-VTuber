"""Local-only static preview with the same asset mounts as the application."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web_tool"


class PreviewHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parts = unquote(urlsplit(path).path).split("/")
        if any(part in ("..", ".") or "\\" in part or "\0" in part for part in parts):
            return str(WEB_ROOT / "__invalid_preview_path__")
        clean = [part for part in parts if part]
        if clean and clean[0] == "live2d-models":
            base, remainder = ROOT / "live2d-models", clean[1:]
        elif clean and clean[0] == "libs":
            base, remainder = ROOT / "frontend" / "libs", clean[1:]
        else:
            base, remainder = WEB_ROOT, clean
        resolved = base.joinpath(*remainder).resolve()
        if not resolved.is_relative_to(base.resolve()):
            return str(WEB_ROOT / "__invalid_preview_path__")
        return str(resolved)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=12401)
    args = parser.parse_args()
    handler = partial(PreviewHandler, directory=str(WEB_ROOT))
    print(f"Persona Studio: http://localhost:{args.port}/platform/", flush=True)
    print("Local preview only; no model API calls. Ctrl+C to stop.", flush=True)
    try:
        with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
