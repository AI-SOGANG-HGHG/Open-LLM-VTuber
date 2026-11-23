"""Exercise the real local Cubism runtime with the existing Mao model, no chat API."""

import os
import json
import hashlib
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright


class Live2DPreviewTests(unittest.TestCase):
    def test_sogangi_real_model_changes_eyes_and_mouth_and_restores_pixels(self):
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
        self.page.locator("#loadSogangi").click()
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.modelUrl==='/live2d-models/sogangi-minimum/runtime/sogangi.model3.json'",
            timeout=30000,
        )
        self.assertIn("ParamMouthOpenY", self.page.locator("#modelFacts").inner_text())
        self.assertTrue(self.page.locator("#parameter-tilt").is_disabled())
        self.assertIn(
            "미연결", self.page.locator("#parameter-tilt").locator("..").inner_text()
        )
        self.assertGreater(self.drawn_pixels(), 10000)
        manifest = self.page.request.get(
            base + "/live2d-models/sogangi-minimum/build-manifest.json"
        ).json()
        moc = self.page.request.get(
            base + "/live2d-models/sogangi-minimum/runtime/sogangi.moc3"
        ).body()
        self.assertEqual(hashlib.sha256(moc).hexdigest(), manifest["moc_sha256"])
        self.assertEqual(manifest["drawables"], 24)
        self.assertEqual(manifest["texture_size"], [2048, 2048])
        self.assertTrue(manifest["native_consistency"])

        def snapshot(name):
            return self.page.evaluate(
                """name => {
              const source=document.querySelector('#modelCanvas'),canvas=document.createElement('canvas');
              canvas.width=source.width;canvas.height=source.height;
              const context=canvas.getContext('2d');context.drawImage(source,0,0);
              const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
              window.__sogangiNativePixels??={};
              window.__sogangiNativePixels[name]=pixels;
              const reference=window.__sogangiNativePixels.neutral;
              return reference ? pixels.filter((value,index)=>value!==reference[index]).length : 0;
            }""",
                name,
            )

        def set_parameter(selector, value):
            frame = int(self.page.locator("#modelStage").get_attribute("data-frames"))
            self.page.locator(selector).evaluate(
                "(input,value)=>{input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}))}",
                value,
            )
            self.page.wait_for_function(
                "frame=>Number(document.querySelector('#modelStage').dataset.frames)>frame+2",
                arg=frame,
            )

        snapshot("neutral")
        set_parameter("#parameter-mouth", 1)
        self.assertGreater(snapshot("open"), 100)
        output = Path("tmp/sogangi-browser/live2d")
        output.mkdir(parents=True, exist_ok=True)
        self.page.locator("#modelCanvas").screenshot(
            path=str(output / "sogangi-mouth-open.png")
        )
        set_parameter("#parameter-mouth", 0)
        self.assertEqual(snapshot("restored"), 0)
        set_parameter("#parameter-eyeL", 0)
        left_difference = snapshot("left-closed")
        self.assertGreater(left_difference, 100)
        set_parameter("#parameter-eyeR", 0)
        self.assertGreater(snapshot("both-closed"), left_difference)
        self.page.locator("#modelCanvas").screenshot(
            path=str(output / "sogangi-eyes-closed.png")
        )
        self.page.locator("#resetPose").click()
        self.page.wait_for_timeout(100)
        self.assertEqual(snapshot("reset"), 0)
        self.page.screenshot(
            path=str(output / "sogangi-minimum-inspector.png"), full_page=True
        )
        self.page.goto(
            base + "/web-tool/sogangi/live2d-preview.html?model=sogangi-minimum",
            wait_until="networkidle",
        )
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.loaded==='true'"
        )
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertFalse(
            self.page.evaluate("document.documentElement.scrollWidth>innerWidth")
        )
        self.page.screenshot(
            path=str(output / "sogangi-minimum-mobile.png"), full_page=True
        )

    def test_rigging_map_matches_artifact_and_exposes_repair_zones(self):
        root = (
            os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
            + "/web-tool/sogangi/"
        )
        mapping = self.page.request.get(root + "workshop/rigging-map/rigging-map.json").json()
        artifact = self.page.request.get(
            root + "assets/production/handoff-manifest.json"
        ).json()
        self.assertEqual(mapping["psd_sha256"], artifact["psd_sha256"])
        self.assertEqual(len(mapping["parts"]), 24)
        self.assertEqual(len(mapping["deformers"]), 9)
        self.page.goto(root + "rigging-map.html", wait_until="networkidle")
        self.assertEqual(self.page.locator("#riggingItems button").count(), 9)
        self.page.locator('[data-rig-mode="underpainting"]').click()
        self.assertEqual(self.page.locator("#riggingItems button").count(), 6)
        self.assertIn("보완 검토 영역", self.page.locator("#riggingFacts").inner_text())
        self.page.locator('[data-rig-mode="parts"]').click()
        self.assertEqual(self.page.locator("#riggingItems button").count(), 24)
        self.page.locator("#riggingItems button").last.click()
        self.assertIn("숨김", self.page.locator("#riggingFacts").inner_text())
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertFalse(
            self.page.evaluate("document.documentElement.scrollWidth>innerWidth")
        )
        output = Path("tmp/sogangi-browser/live2d")
        output.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(
            path=str(output / "rigging-map-mobile.png"), full_page=True
        )
        self.page.goto(root + "live2d-plan.html", wait_until="networkidle")
        self.page.locator('[data-preview-expression="joy"]').click()
        self.page.wait_for_function(
            "document.querySelector('#motionPreview').dataset.expression==='joy' && document.querySelector('#motionPreview').dataset.eyeOpen==='0.00,0.00'"
        )
        self.page.screenshot(
            path=str(output / "sogangi-joy-preview.png"), full_page=True
        )
        self.page.locator('[data-preview-expression="neutral"]').click()
        self.page.wait_for_function(
            "document.querySelector('#motionPreview').dataset.expression==='neutral'"
        )

    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get(
                "SOGANGI_BROWSER",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            ),
            headless=True,
            args=["--enable-unsafe-swiftshader"],
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 1000})
        self.errors = []
        self.sockets = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("websocket", lambda socket: self.sockets.append(socket.url))
        self.page.goto(
            os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
            + "/web-tool/sogangi/live2d-preview.html",
            wait_until="networkidle",
        )

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.assertEqual(self.sockets, [])
        self.page.close()

    def load_mao(self):
        previous = self.page.locator("#modelStage").get_attribute("data-revision")
        self.page.locator("#loadModel").click()
        self.page.wait_for_function(
            "previous => (document.querySelector('#modelStage').dataset.revision && document.querySelector('#modelStage').dataset.revision!==previous) || document.querySelector('#previewStatus').dataset.error==='true'",
            arg=previous,
            timeout=30000,
        )

    def drawn_pixels(self):
        return self.page.locator("#modelCanvas").evaluate("""async canvas => {
          const image=new Image();image.src=canvas.toDataURL();await image.decode();
          const output=document.createElement('canvas');output.width=canvas.width;output.height=canvas.height;
          const context=output.getContext('2d');context.drawImage(image,0,0);
          return context.getImageData(0,0,output.width,output.height).data.filter((value,index)=>index%4===3 && value>0).length;
        }""")

    def test_reload_keeps_textures_and_selected_motion_does_not_play_audio(self):
        url = (
            os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
            + "/live2d-models/mao_pro/runtime/mao_pro.model3.json"
        )
        settings = self.page.request.get(url).json()
        settings["FileReferences"]["Motions"]["Idle"][0]["Sound"] = (
            "unexpected-preview-audio.wav"
        )
        self.page.route(
            "**/mao_pro.model3.json",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(settings)
            ),
        )
        requests = []
        self.page.on("request", lambda request: requests.append(request.url))
        for _ in range(3):
            self.load_mao()
            self.page.wait_for_timeout(100)
            self.assertGreater(self.drawn_pixels(), 10000)
        self.page.locator("#modelMotion").select_option("Idle")
        self.page.locator("#modelMotionEntry").select_option("0")
        self.page.locator("#playMotion").click()
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.motionGroup==='Idle'"
        )
        self.assertEqual(
            self.page.locator("#modelStage").get_attribute("data-motion-index"), "0"
        )
        self.assertFalse(any("unexpected-preview-audio" in url for url in requests))
        self.assertEqual(
            self.page.locator("#previewStatus").get_attribute("data-error"),
            "false",
            self.page.locator("#previewStatus").inner_text(),
        )

    def test_real_model_draws_and_manual_mouth_closes(self):
        self.load_mao()
        self.assertIn("ParamA", self.page.locator("#modelFacts").inner_text())
        self.assertGreater(self.page.locator("#parameterControls input").count(), 2)
        self.page.wait_for_function(
            "Number(document.querySelector('#modelStage').dataset.frames)>5"
        )
        opaque = self.drawn_pixels()
        self.assertGreater(opaque, 10000)
        self.page.locator("#mouthSweep").click()
        self.page.wait_for_function(
            "Number(document.querySelector('#modelStage').dataset.appliedMouth)>.5"
        )
        output = Path("tmp/sogangi-browser/live2d")
        output.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(output / "mao-mouth-open.png"), full_page=True)
        self.page.locator("#resetPose").click()
        self.page.wait_for_function(
            "Number(document.querySelector('#modelStage').dataset.appliedMouth)===0"
        )
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.screenshot(path=str(output / "mao-mobile.png"), full_page=True)
        self.assertFalse(
            self.page.evaluate("document.documentElement.scrollWidth>innerWidth")
        )

    def test_external_or_missing_model_does_not_replace_a_loaded_model(self):
        self.load_mao()
        original = self.page.locator("#modelStage").get_attribute("data-model-url")
        for path in [
            "https://example.invalid/model.model3.json",
            "/live2d-models/../conf.yaml",
            "/live2d-models/sogangi/runtime/sogangi.model3.json",
        ]:
            self.page.locator("#modelUrl").fill(path)
            self.page.locator("#loadModel").click()
            self.page.wait_for_function(
                "document.querySelector('#previewStatus').dataset.error==='true'"
            )
            self.assertEqual(
                self.page.locator("#modelStage").get_attribute("data-model-url"),
                original,
            )
        settings = self.page.request.get(
            os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393") + original
        ).json()
        settings["Groups"] = None
        revision = self.page.locator("#modelStage").get_attribute("data-revision")
        self.page.route(
            "**/mao_pro.model3.json",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(settings)
            ),
        )
        self.page.locator("#modelUrl").fill(original)
        self.page.locator("#loadModel").click()
        self.page.wait_for_function(
            "document.querySelector('#previewStatus').dataset.error==='true'"
        )
        self.assertEqual(
            self.page.locator("#modelStage").get_attribute("data-revision"), revision
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
