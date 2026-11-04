"""Static-reference checks only; synthetic MOC headers are not real renderable models."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.check_live2d_bundle import check_bundle


class Live2DBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name, "bundle")
        self.root.mkdir()
        self.model_path = self.root / "test.model3.json"
        (self.root / "test.moc3").write_bytes(b"MOC3synthetic-static-check-only")
        (self.root / "test.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.root / "idle.motion3.json").write_text("{}")
        expressions = []
        for name in ["neutral", "joy", "sadness", "surprise", "anger"]:
            (self.root / f"{name}.exp3.json").write_text("{}")
            expressions.append({"Name": name, "File": f"{name}.exp3.json"})
        self.model = {
            "Version": 3,
            "FileReferences": {
                "Moc": "test.moc3",
                "Textures": ["test.png"],
                "Expressions": expressions,
                "Motions": {"Idle": [{"File": "idle.motion3.json"}]},
            },
            "Groups": [
                {"Name": "EyeBlink", "Ids": ["ParamEyeLOpen", "ParamEyeROpen"]},
                {"Name": "LipSync", "Ids": ["ParamMouthOpenY"]},
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def check(self, model=None, entry=None):
        self.model_path.write_text(
            json.dumps(self.model if model is None else model), encoding="utf-8"
        )
        return check_bundle(self.model_path, sogangi=True, model_entry=entry)

    def test_static_success_explicitly_does_not_claim_moc3_or_runtime_validation(self):
        result = self.check()
        self.assertTrue(result["ok"], result)
        self.assertTrue(
            any("do not validate MOC3 internals" in text for text in result["warnings"])
        )

    def test_existing_file_outside_bundle_and_windows_paths_are_rejected(self):
        Path(self.temp.name, "outside.moc3").write_bytes(b"MOC3outside")
        for value in [
            "../outside.moc3",
            "C:/outside.moc3",
            "C:outside.moc3",
            "\\server\\share\\model.moc3",
            "bad\x00file.moc3",
            "https://example.invalid/model.moc3",
        ]:
            with self.subTest(value=value):
                model = copy.deepcopy(self.model)
                model["FileReferences"]["Moc"] = value
                result = self.check(model)
                self.assertFalse(result["ok"])
                self.assertNotIn(value, result["checked_files"])

    def test_malformed_groups_expressions_motions_and_mapping_report_errors(self):
        for key, value in [
            ("Groups", None),
            ("Groups", [{"Name": [], "Ids": []}]),
            ("Expressions", [{"Name": {}, "File": "joy.exp3.json"}]),
            ("Motions", {"Idle": None}),
        ]:
            with self.subTest(key=key, value=value):
                model = copy.deepcopy(self.model)
                if key == "Groups":
                    model[key] = value
                else:
                    model["FileReferences"][key] = value
                self.assertFalse(self.check(model)["ok"])
        self.assertFalse(self.check(entry={"emotionMap": []})["ok"])

    def test_expression_order_indices_and_empty_idle_group_fail_handoff_contract(self):
        model = copy.deepcopy(self.model)
        model["FileReferences"]["Expressions"].reverse()
        self.assertFalse(self.check(model)["ok"])
        self.assertFalse(
            self.check(
                entry={"emotionMap": {"joy": 99}, "idleMotionGroupName": "missing"}
            )["ok"]
        )
        model = copy.deepcopy(self.model)
        model["FileReferences"]["Motions"]["Idle"] = []
        self.assertFalse(self.check(model)["ok"])
