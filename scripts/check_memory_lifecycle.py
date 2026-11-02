"""Check persisted Mem0 isolation and scoped deletion in a synthetic pilot store."""

import argparse
import json
import os
from pathlib import Path

from evaluate_memory import Mem0Store, SCOPE, TranscriptStore, write_json
from open_llm_vtuber.memory.store import MemoryScope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    summary = json.loads((args.output / "summary.json").read_text(encoding="utf-8"))
    if summary["backend"] != "mem0" or summary["noise_events"] < 8:
        parser.error("Expected a synthetic Mem0 pilot output")
    settings = summary["settings"]
    key = os.environ.get(settings["api_key_env"], "").strip()
    if not key and args.key_file:
        key = args.key_file.read_text(encoding="utf-8").strip()
    if not key:
        parser.error("API key is required")
    memory = Mem0Store.local(settings, key, args.output / "mem0")
    transcript = TranscriptStore(args.output / "transcripts.db")
    result = {}
    try:
        added = json.loads((args.output / "ingestion.json").read_text(encoding="utf-8"))
        allowed = {
            item["id"]
            for event in added
            if event["event_id"]
            in {"drink", "project", "poster", "meeting-old", "meeting-new"}
            for item in event["result"]["results"]
        }
        foreign = [
            MemoryScope("viewer-b", "sora", "room-a"),
            MemoryScope("viewer-a", "luna", "room-a"),
            MemoryScope("viewer-a", "sora", "room-b"),
        ]
        hits = memory.search(SCOPE, "내 반려묘 이름이 뭐였지?")
        result["primary_scope_has_no_foreign_memory_ids"] = bool(hits) and all(
            hit["id"] in allowed for hit in hits
        )
        result["foreign_scopes_have_their_own_memory"] = all(
            memory.search(scope, "반려묘 이름") for scope in foreign
        )
        # Delete only the synthetic room-b fixture, preserving the primary pilot.
        target = foreign[-1]
        memory.forget(target)
        transcript.forget(target)
        result["deleted_scope_search_empty"] = (
            memory.search(target, "반려묘 이름") == []
        )
        result["deleted_scope_transcript_empty"] = transcript.recent(target) == []
        result["neighbor_memory_preserved"] = bool(
            memory.search(SCOPE, "프로젝트 이름")
        )
        result["neighbor_transcript_preserved"] = bool(transcript.recent(SCOPE))
    finally:
        memory.close()
        transcript.close()
    write_json(args.output / "lifecycle.json", result)
    print(json.dumps(result, indent=2))
    if not all(result.values()):
        raise SystemExit("Lifecycle checks failed")


if __name__ == "__main__":
    main()
