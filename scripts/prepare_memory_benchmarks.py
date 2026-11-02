"""Download pinned public benchmark artifacts, recording exact bytes and hashes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def prepare(output: Path, sources_path: Path):
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    prior_path = output / "manifest.json"
    prior = (
        json.loads(prior_path.read_text(encoding="utf-8"))
        if prior_path.exists()
        else {"files": []}
    )
    known_hashes = {row["url"]: row["sha256"] for row in prior["files"]}
    records = []
    for name, spec in sources.items():
        if "repo" in spec:
            base = (
                f"https://raw.githubusercontent.com/{spec['repo']}/{spec['revision']}/"
            )
        else:
            base = f"https://huggingface.co/datasets/{spec['dataset']}/resolve/{spec['revision']}/"
        for filename in spec["files"]:
            target = output / name / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                request = urllib.request.Request(
                    base + filename, headers={"User-Agent": "persona-memory-benchmark"}
                )
                partial = target.with_name(target.name + ".partial")
                with (
                    urllib.request.urlopen(request, timeout=120) as response,
                    partial.open("wb") as file,
                ):
                    while chunk := response.read(1024 * 1024):
                        file.write(chunk)
                partial.replace(target)
            digest_hash = hashlib.sha256()
            with target.open("rb") as file:
                while chunk := file.read(1024 * 1024):
                    digest_hash.update(chunk)
            digest = digest_hash.hexdigest()
            if (
                base + filename in known_hashes
                and known_hashes[base + filename] != digest
            ):
                raise ValueError(f"Cached benchmark artifact changed: {target}")
            records.append(
                {
                    "group": name,
                    "path": str(target.relative_to(output)).replace("\\", "/"),
                    "url": base + filename,
                    "revision": spec["revision"],
                    "license": spec["license"],
                    "size_bytes": target.stat().st_size,
                    "sha256": digest,
                }
            )
            print(
                f"Ready: {name}/{filename} ({target.stat().st_size:,} bytes)",
                flush=True,
            )
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sources_sha256": hashlib.sha256(sources_path.read_bytes()).hexdigest(),
        "files": records,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/memory-benchmarks")
    parser.add_argument(
        "--sources",
        type=Path,
        default=ROOT / "experiments/memory/benchmarks.sources.json",
    )
    args = parser.parse_args()
    prepare(args.output, args.sources)
