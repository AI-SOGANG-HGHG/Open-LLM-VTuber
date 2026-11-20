"""The review map must stay attached to the exact prepared art and parameter names."""

import json
from pathlib import Path
import unittest


class RiggingContractTests(unittest.TestCase):
    def setUp(self):
        root = Path("web_tool/sogangi")
        self.mapping = json.loads(
            (root / "workshop/rigging-map/rigging-map.json").read_text(encoding="utf-8")
        )
        self.art = json.loads(
            (root / "assets/production/handoff-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.spec = json.loads((root / "workshop/live2d-plan/live2d-spec.json").read_text(encoding="utf-8"))

    def test_map_uses_exact_artifact_layers_and_canvas(self):
        self.assertEqual(self.mapping["psd_sha256"], self.art["psd_sha256"])
        self.assertEqual(
            {item["id"] for item in self.mapping["parts"]},
            {item["name"] for item in self.art["parts"]},
        )
        width = self.mapping["canvas"]["width"]
        height = self.mapping["canvas"]["height"]
        self.assertEqual(
            (width, height), (self.art["canvas"]["width"], self.art["canvas"]["height"])
        )
        for part in self.mapping["parts"]:
            x, y, w, h = part["bounds"]
            self.assertTrue(
                0 <= x < x + w <= width and 0 <= y < y + h <= height, part["id"]
            )

    def test_proposed_hierarchy_and_parameter_bindings_have_no_dangling_references(
        self,
    ):
        deformers = {item["id"]: item for item in self.mapping["deformers"]}
        parts = {item["id"] for item in self.mapping["parts"]}
        parameters = {item["id"]: item for item in self.spec["parameters"]}
        for item in deformers.values():
            self.assertTrue(set(item["parts"]) <= parts)
            visited = set()
            current = item
            while current.get("parent"):
                self.assertNotIn(current["id"], visited, "cyclic deformer hierarchy")
                visited.add(current["id"])
                self.assertIn(current["parent"], deformers)
                current = deformers[current["parent"]]
        for binding in self.mapping["bindings"]:
            self.assertIn(binding["deformer"], deformers)
            self.assertIn(binding["parameter"], parameters)
            limits = parameters[binding["parameter"]]
            self.assertTrue(
                all(
                    limits["min"] <= value <= limits["max"]
                    for value in binding["initial_keys"]
                )
            )
        self.assertIn("ParamArmRWave", parameters)
