"""Persona checks must never start paid requests implicitly or exceed the selected budget."""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
import unittest
from unittest.mock import patch

from tools import evaluate_sogangi


class PersonaEvaluationCliTests(unittest.TestCase):
    def test_default_invocation_is_a_zero_call_dry_run(self):
        output = io.StringIO()
        with (
            patch("sys.argv", ["evaluate_sogangi.py"]),
            patch.object(evaluate_sogangi.asyncio, "run") as execute,
            redirect_stdout(output),
        ):
            evaluate_sogangi.main()
        execute.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["api_calls"], 0)
        self.assertEqual(result["maximum_calls"], 8)

    def test_invalid_or_over_budget_selection_is_rejected_before_execution(self):
        for args in [
            ["--live", "--case", "memory-correction", "--max-calls", "1"],
            ["--live", "--case", "unknown"],
            ["--live", "--max-calls", "999"],
        ]:
            with self.subTest(args=args):
                with (
                    patch("sys.argv", ["evaluate_sogangi.py", *args]),
                    patch.object(evaluate_sogangi.asyncio, "run") as execute,
                    redirect_stderr(io.StringIO()),
                ):
                    with self.assertRaises(SystemExit) as stopped:
                        evaluate_sogangi.main()
                self.assertEqual(stopped.exception.code, 2)
                execute.assert_not_called()
