"""Actual emotion variants and exported exp3 files; no model/TTS service calls."""

import json
from pathlib import Path
import unittest

from sogangi_motion import SogangiMotionTests


class SogangiExpressionTests(SogangiMotionTests):
    def load_expressions(self):
        self.page.locator("#loadSogangiExpressions").click()
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.modelUrl?.includes('sogangi-expressions')"
        )
        self.page.wait_for_timeout(100)

    def test_expression_geometry_preserves_neutral_and_independent_blink_lip_sync(self):
        self.page.locator("#loadSogangiGreeting").click()
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.loaded==='true'"
        )
        self.page.wait_for_timeout(100)
        self.snapshot(reference=True)
        output = Path("tmp/sogangi-browser/expressions")
        output.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(output / "baseline.png"), full_page=True)
        self.load_expressions()
        self.page.screenshot(path=str(output / "new-neutral.png"), full_page=True)
        self.assertEqual(self.snapshot()["different"], 0)
        for mood, name in [(1, "anger"), (2, "surprise")]:
            self.set_pose(mood=mood, mouth=0, eyeL=1, eyeR=1)
            self.assertGreater(self.snapshot()["different"], 200)
            self.page.screenshot(
                path=str(output / (name + "-closed.png")), full_page=True
            )
            self.snapshot(pose_reference=True)
            self.set_pose(mouth=1)
            self.assertGreater(self.snapshot()["pose_difference"], 100)
            self.page.screenshot(
                path=str(output / (name + "-speaking.png")), full_page=True
            )
            self.snapshot(pose_reference=True)
            self.set_pose(eyeL=0, eyeR=0)
            self.assertGreater(self.snapshot()["pose_difference"], 100)
            self.set_pose(tilt=-30, breath=1, wave=1)
            self.assertGreater(self.snapshot()["drawn"], 10000)
            values = json.loads(
                self.page.locator("#modelStage").get_attribute(
                    "data-applied-parameters"
                )
            )
            self.assertEqual(values["ParamMouthOpenY"], 1)
            self.assertEqual(values["ParamFaceMood"], mood)
            self.assertEqual(values["ParamEyeLOpen"], 0)
            self.set_pose(tilt=0, breath=0, wave=0)
        self.page.locator("#resetPose").click()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.snapshot()["different"], 0)

    def test_exported_expression_files_apply_in_actual_core_without_forcing_mouth(self):
        self.load_expressions()
        settings = self.page.request.get(
            self.page.url.split("/web-tool/")[0]
            + "/live2d-models/sogangi-expressions/runtime/sogangi.model3.json"
        ).json()
        entries = settings["FileReferences"]["Expressions"]
        self.assertEqual(
            [item["Name"] for item in entries], ["neutral", "joy", "anger", "surprise"]
        )
        for entry in entries:
            item = self.page.request.get(
                self.page.url.split("/web-tool/")[0]
                + "/live2d-models/sogangi-expressions/runtime/"
                + entry["File"]
            ).json()
            self.assertFalse(
                any(
                    parameter["Id"].startswith("ParamMouth")
                    for parameter in item["Parameters"]
                )
            )
        self.page.locator("#manualMode").uncheck()
        for index, mood in [("2", 1), ("3", 2), ("0", 0)]:
            self.page.locator("#modelExpression").select_option(index)
            self.page.wait_for_function(
                "mood=>JSON.parse(document.querySelector('#modelStage').dataset.appliedParameters).ParamFaceMood===mood",
                arg=mood,
            )
        self.page.locator("#modelExpression").select_option("1")
        self.page.wait_for_function(
            "JSON.parse(document.querySelector('#modelStage').dataset.appliedParameters).ParamEyeLOpen===0"
        )


if __name__ == "__main__":
    suite = unittest.TestSuite(
        [
            SogangiExpressionTests(
                "test_expression_geometry_preserves_neutral_and_independent_blink_lip_sync"
            ),
            SogangiExpressionTests(
                "test_exported_expression_files_apply_in_actual_core_without_forcing_mouth"
            ),
        ]
    )
    raise SystemExit(
        not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    )
