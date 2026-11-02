import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/memory"))
sys.path.insert(0, str(ROOT / "scripts"))

from benchmark_data import (  # noqa: E402
    BenchmarkCase,
    LexicalRetriever,
    documents,
    evidence_metrics,
    load_longmemeval,
    load_heard,
    model_document,
    pack_documents,
    select_cases,
)
from benchmark_memory_live import read_jsonl, memory_blocks, rate_limit_cause  # noqa: E402
from longmemeval_official import get_anscheck_prompt  # noqa: E402
from benchmark_api import BenchmarkAPI  # noqa: E402


class BenchmarkTests(unittest.TestCase):
    def case(self):
        return BenchmarkCase(
            "q",
            "multi-session",
            "my favorite tea",
            "2023/01/05",
            [
                {
                    "session_id": "answer_secret",
                    "date": "2023/01/01",
                    "turns": [
                        {"role": "user", "content": "My favorite tea is barley tea"},
                        {
                            "role": "assistant",
                            "content": "Your earlier discount was fifteen percent",
                        },
                    ],
                },
                {
                    "session_id": "other_secret",
                    "date": "2023/01/02",
                    "turns": [{"role": "user", "content": "A second date is Tuesday"}],
                },
            ],
            "GOLD_ANSWER_SENTINEL",
            ["answer_secret", "other_secret"],
        )

    def test_both_roles_retained_without_gold_or_telltale_session_ids(self):
        case = self.case()
        docs = documents(case)
        model_text = json.dumps([model_document(d) for d in docs])
        self.assertIn("fifteen percent", model_text)
        self.assertNotIn("GOLD_ANSWER_SENTINEL", model_text)
        self.assertNotIn("answer_secret", model_text)
        self.assertNotIn("other_secret", model_text)
        self.assertNotIn("GOLD_ANSWER_SENTINEL", "".join(memory_blocks(case)))

    def test_longmemeval_loader_strips_turn_level_answer_flags(self):
        case = self.case()
        row = {
            "question_id": "q_abs",
            "question_type": "single-session-user",
            "question": "q",
            "question_date": "date",
            "answer": "gold",
            "answer_session_ids": [],
            "haystack_session_ids": ["s"],
            "haystack_dates": ["date"],
            "haystack_sessions": [
                [{"role": "user", "content": "evidence", "has_answer": True}]
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            path.write_text(json.dumps([row]), encoding="utf-8")
            case = load_longmemeval(path)[0]
        self.assertEqual(case.category, "abstention")
        self.assertEqual(
            case.sessions[0]["turns"], [{"role": "user", "content": "evidence"}]
        )

    def test_assistant_fact_is_retrievable(self):
        retriever = LexicalRetriever(documents(self.case()))
        try:
            hits = retriever.search("What was my earlier discount?", 1)
            self.assertEqual(hits[0]["role"], "assistant")
            self.assertIn("fifteen", hits[0]["text"])
        finally:
            retriever.close()

    def test_multi_session_recall_is_not_any_hit(self):
        case = self.case()
        metrics = evidence_metrics(case, documents(case)[:1])
        self.assertEqual(metrics["gold_session_recall"], 0.5)
        self.assertFalse(metrics["all_gold_sessions_found"])
        self.assertTrue(
            evidence_metrics(case, documents(case))["all_gold_sessions_found"]
        )

    def test_session_hit_does_not_imply_answer_turn_hit(self):
        case = self.case()
        case.evidence_turn_ids = ["s000-t001"]
        metrics = evidence_metrics(case, documents(case)[:1])
        self.assertEqual(metrics["gold_session_recall"], 0.5)
        self.assertEqual(metrics["gold_turn_hit_fraction"], 0)
        self.assertFalse(metrics["all_gold_turns_hit"])

    def test_korean_loader_excludes_future_and_other_personas(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "heard_corpus/data/raw/utterances.jsonl"
            qa = root / "heard_ko/data/ko_native/test.jsonl"
            raw.parent.mkdir(parents=True)
            qa.parent.mkdir(parents=True)
            utterances = [
                {
                    "utt_id": "past",
                    "persona_id": "a",
                    "timestamp": "2026-01-01",
                    "text": "Known fact",
                },
                {
                    "utt_id": "future",
                    "persona_id": "a",
                    "timestamp": "2026-03-01",
                    "text": "Future fact",
                },
                {
                    "utt_id": "other",
                    "persona_id": "b",
                    "timestamp": "2026-01-01",
                    "text": "Other person's fact",
                },
            ]
            raw.write_text(
                "".join(json.dumps(row) + "\n" for row in utterances), encoding="utf-8"
            )
            question = {
                "item_id": "q",
                "ability": "IE",
                "persona_id": "a",
                "question": {"timestamp": "2026-02-01", "text": "q"},
                "gold_answer": {"text": "answer", "evidence_utt_ids": ["past"]},
            }
            qa.write_text(json.dumps(question) + "\n", encoding="utf-8")
            case = load_heard(root)[0]
            self.assertEqual([s["session_id"] for s in case.sessions], ["past"])
            question["gold_answer"]["evidence_utt_ids"] = ["future"]
            qa.write_text(json.dumps(question) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_heard(root)

    def test_wrapped_sdk_rate_limit_can_be_retried(self):
        quota = RuntimeError("quota")
        quota.status_code = 429
        wrapped = RuntimeError("SDK LLMError")
        wrapped.__cause__ = quota
        self.assertIs(rate_limit_cause(wrapped), quota)
        self.assertIsNone(rate_limit_cause(ValueError("bad input")))

    def test_daily_quota_is_not_retried_like_a_minute_limit(self):
        class RateLimitError(Exception):
            body = {
                "error": {
                    "details": [
                        {
                            "violations": [
                                {
                                    "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                                    "quotaValue": "20",
                                }
                            ]
                        }
                    ]
                }
            }

        with tempfile.TemporaryDirectory() as directory:
            api = BenchmarkAPI.__new__(BenchmarkAPI)
            api.settings = {"model": "judge"}
            api.log = Path(directory) / "calls.jsonl"
            api.interval = api.last_call = 0
            api.client = Mock()
            api.client.chat.completions.create.side_effect = RateLimitError("quota")
            with patch("benchmark_api.time.sleep") as sleep:
                with self.assertRaises(RuntimeError):
                    api.chat([{"role": "user", "content": "test"}], "test")
            self.assertEqual(api.client.chat.completions.create.call_count, 1)
            self.assertNotIn(15, [call.args[0] for call in sleep.call_args_list])
            self.assertTrue(read_jsonl(api.log)[0]["quota"]["daily_exhausted"])

    def test_budget_metrics_use_only_evidence_actually_passed(self):
        case = self.case()
        docs = documents(case)
        docs[0]["text"] = "x" * 10000
        selected = pack_documents(docs[:1], 1000)
        self.assertEqual(selected, [])
        self.assertEqual(evidence_metrics(case, selected)["gold_session_recall"], 0)

    def test_stratified_selection_is_independent_of_input_order(self):
        cases = [
            BenchmarkCase(str(i), "a" if i % 2 else "b", "q", "date", [], "", [])
            for i in range(20)
        ]
        self.assertEqual(
            [c.question_id for c in select_cases(cases)],
            [c.question_id for c in select_cases(list(reversed(cases)))],
        )
        self.assertEqual(len(select_cases(cases)), 2)

    def test_jsonl_preserves_unicode_line_separators_in_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r.jsonl"
            row = {"text": "before\u2028after\u0085still one JSON object"}
            path.write_text(
                json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            self.assertEqual(read_jsonl(path), [row])

    def test_official_abstention_and_update_rules_are_distinct(self):
        abstention = get_anscheck_prompt(
            "single-session-user", "q", "explanation", "response", abstention=True
        )
        update = get_anscheck_prompt("knowledge-update", "q", "new value", "response")
        self.assertIn("unanswerable", abstention)
        self.assertIn("updated answer", update)

    def test_vendored_prompt_matches_pinned_upstream_ast_when_available(self):
        path = (
            ROOT
            / "tmp/memory-benchmarks/longmemeval_code/src/evaluation/evaluate_qa.py"
        )
        if not path.exists():
            self.skipTest("Public benchmark assets not downloaded")
        official = ast.parse(path.read_text(encoding="utf-8"))
        vendor = ast.parse(
            (ROOT / "experiments/memory/longmemeval_official.py").read_text(
                encoding="utf-8"
            )
        )

        def get_function(tree):
            return next(
                node
                for node in tree.body
                if isinstance(node, ast.FunctionDef)
                and node.name == "get_anscheck_prompt"
            )

        self.assertEqual(
            ast.dump(get_function(official)), ast.dump(get_function(vendor))
        )


if __name__ == "__main__":
    unittest.main()
