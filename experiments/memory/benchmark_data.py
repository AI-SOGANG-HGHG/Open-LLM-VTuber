"""Benchmark inputs and retrieval. Labels are kept outside model-facing documents."""

from collections import defaultdict
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sqlite3


@dataclass
class BenchmarkCase:
    question_id: str
    category: str
    question: str
    question_date: str
    sessions: list[dict]
    answer: str
    evidence_session_ids: list[str]
    evidence_turn_ids: list[str] = field(default_factory=list)


def load_longmemeval(path: Path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for row in rows:
        if (
            len(
                {
                    len(row[k])
                    for k in (
                        "haystack_session_ids",
                        "haystack_dates",
                        "haystack_sessions",
                    )
                }
            )
            != 1
        ):
            raise ValueError("Misaligned session/date arrays")
        sessions = []
        gold_turns = []
        for session_index, (sid, date, turns) in enumerate(
            zip(
                row["haystack_session_ids"],
                row["haystack_dates"],
                row["haystack_sessions"],
            )
        ):
            gold_turns.extend(
                f"s{session_index:03}-t{turn_index:03}"
                for turn_index, turn in enumerate(turns)
                if turn.get("has_answer")
            )
            sessions.append(
                {
                    "session_id": sid,
                    "date": date,
                    "turns": [
                        {"role": t["role"], "content": t["content"]} for t in turns
                    ],
                }
            )
        cases.append(
            BenchmarkCase(
                row["question_id"],
                "abstention"
                if row["question_id"].endswith("_abs")
                else row["question_type"],
                row["question"],
                row["question_date"],
                sessions,
                row["answer"],
                row["answer_session_ids"],
                gold_turns,
            )
        )
    if len({case.question_id for case in cases}) != len(cases):
        raise ValueError("Duplicate question IDs")
    return cases


def select_cases(cases, per_category=1, seed=20261102):
    if per_category == 0:
        return cases
    buckets = defaultdict(list)
    for case in cases:
        buckets[case.category].append(case)
    selected = []
    for category in sorted(buckets):
        ordered = sorted(
            buckets[category],
            key=lambda c: hashlib.sha256(
                f"{seed}:{c.question_id}".encode()
            ).hexdigest(),
        )
        selected.extend(ordered[:per_category])
    return selected


def split_text(text, size=2400, overlap=150):
    if size <= overlap or overlap < 0:
        raise ValueError("Expected size > overlap >= 0")
    return [text[start : start + size] for start in range(0, len(text), size - overlap)]


def documents(case, chunk_chars=2400):
    docs = []
    # Do not expose 'answer_*' session IDs, has_answer, operations, or gold fields.
    for index, session in enumerate(case.sessions):
        for turn_index, turn in enumerate(session["turns"]):
            if turn["role"] not in {"user", "assistant"}:
                raise ValueError("Unexpected historical role")
            for part, text in enumerate(split_text(turn["content"], chunk_chars)):
                docs.append(
                    {
                        "id": f"s{index:03}-t{turn_index:03}-p{part:03}",
                        "session_id": session["session_id"],
                        "date": session["date"],
                        "role": turn["role"],
                        "text": text,
                    }
                )
    return docs


def model_document(doc):
    return {key: doc[key] for key in ("id", "date", "role", "text")}


STOPWORDS = set(
    "a an the this that these those is are was were am be been being i me my we our you your he she it they them their of to for in on at by with and or but as from what which who when where how why did do does have has had can could would should about please tell remind remember previously earlier before".split()
)


class LexicalRetriever:
    def __init__(self, docs):
        self.docs = docs
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE VIRTUAL TABLE corpus USING fts5(text)")
        self.db.executemany(
            "INSERT INTO corpus(rowid,text) VALUES(?,?)",
            [(i + 1, doc["text"]) for i, doc in enumerate(docs)],
        )

    def search(self, query, k):
        terms = sorted(
            {
                word.lower()
                for word in re.findall(r"[^\W_]+", query)
                if word.lower() not in STOPWORDS
            }
        )[:128]
        if not terms:
            return []
        expression = " OR ".join('"' + term + '"' for term in terms)
        rows = self.db.execute(
            "SELECT rowid FROM corpus WHERE corpus MATCH ? ORDER BY bm25(corpus),rowid LIMIT ?",
            (expression, k),
        ).fetchall()
        return [self.docs[row[0] - 1] for row in rows]

    def close(self):
        self.db.close()


def evidence_metrics(case, selected):
    if case.category == "abstention":
        return {
            "gold_session_recall": None,
            "all_gold_sessions_found": None,
            "gold_turn_hit_fraction": None,
            "all_gold_turns_hit": None,
        }
    gold = set(case.evidence_session_ids)
    if not gold:
        raise ValueError("Answerable question without evidence sessions")
    found = {doc["session_id"] for doc in selected}
    gold_turns = set(case.evidence_turn_ids)
    found_turns = {doc["id"].rsplit("-p", 1)[0] for doc in selected}
    return {
        "gold_session_recall": len(gold & found) / len(gold),
        "all_gold_sessions_found": gold.issubset(found),
        "gold_turn_hit_fraction": len(gold_turns & found_turns) / len(gold_turns)
        if gold_turns
        else None,
        "all_gold_turns_hit": gold_turns.issubset(found_turns) if gold_turns else None,
    }


def pack_documents(docs, char_budget=24000):
    selected = []
    for doc in docs:
        candidate = selected + [doc]
        if (
            len(json.dumps([model_document(d) for d in candidate], ensure_ascii=False))
            <= char_budget
        ):
            selected = candidate
    return selected


def manifest_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_heard(assets):
    with (assets / "heard_corpus/data/raw/utterances.jsonl").open(
        encoding="utf-8"
    ) as file:
        corpus = [json.loads(line) for line in file if line.strip()]
    with (assets / "heard_ko/data/ko_native/test.jsonl").open(encoding="utf-8") as file:
        questions = [json.loads(line) for line in file if line.strip()]
    cases = []
    for row in questions:
        if row["ability"] == "REFL":
            continue  # Pairwise reflective evaluation is separate from factual QA.
        cutoff = row["question"]["timestamp"]
        available = [
            u
            for u in corpus
            if u["persona_id"] == row["persona_id"] and u["timestamp"] <= cutoff
        ]
        gold = row["gold_answer"].get("evidence_utt_ids", [])
        if not set(gold).issubset({u["utt_id"] for u in available}):
            raise ValueError(
                "Korean gold evidence missing, cross-persona or in the future"
            )
        sessions = [
            {
                "session_id": u["utt_id"],
                "date": u["timestamp"],
                "turns": [{"role": "user", "content": u["text"]}],
            }
            for u in sorted(available, key=lambda u: u["timestamp"])
        ]
        category = "abstention" if row["ability"] == "ABS" else "ko-" + row["ability"]
        cases.append(
            BenchmarkCase(
                row["item_id"],
                category,
                row["question"]["text"],
                cutoff,
                sessions,
                row["gold_answer"]["text"],
                gold,
            )
        )
    return cases


def load_memops_adjacent(assets):
    cases = []
    for path in sorted(
        (
            assets / "memops_adjacent_preview/generated_result/2-evidence_conversation"
        ).glob("*.json")
    ):
        row = json.loads(path.read_text(encoding="utf-8"))
        eligible = [
            q for q in row["answer"] if q["evaluation_setting"] == "adjacent_operation"
        ]
        preferred = (
            "StateTrajectory"
            if row["operation_type"] == "TrajectoryOps"
            else "StateTransition"
        )
        question = next(
            (q for q in eligible if q["evaluation_type"] == preferred), eligible[-1]
        )
        sessions = [
            {
                "session_id": str(segment["segment_index"]),
                "date": f"segment-{segment['segment_index']:03}",
                "turns": [
                    {"role": turn["role"], "content": turn["content"]}
                    for turn in segment["dialogue"]
                ],
            }
            for segment in row["conversations"]
        ]
        qtext = question["question"]
        if question.get("candidate_options"):
            qtext += "\nOptions: " + json.dumps(
                question["candidate_options"], ensure_ascii=False
            )
        cases.append(
            BenchmarkCase(
                path.stem + ":" + question["question_pair_id"],
                row["operation_type"],
                qtext,
                "After the last provided segment",
                sessions,
                question["expected_answer"],
                [],
            )
        )
    return cases
