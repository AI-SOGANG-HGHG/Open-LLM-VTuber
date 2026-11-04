"""Check real art assets, comparison controls and the downloadable candidate PSD.

No chat socket, model or voice API is used. Pixel equality checks the reviewed
neutral-pose contract, not artistic quality or Cubism import compatibility.
"""

import hashlib
import json
import os
from pathlib import Path
import unittest
import zipfile

from playwright.sync_api import sync_playwright


class ArtReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get(
                "SOGANGI_BROWSER",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            ),
            headless=True,
        )
        cls.root = (
            os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
            + "/web-tool/sogangi/"
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(
            viewport={"width": 1440, "height": 1100}, accept_downloads=True
        )
        self.errors = []
        self.sockets = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("websocket", lambda socket: self.sockets.append(socket.url))
        self.page.goto(self.root + "art-review.html", wait_until="networkidle")

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.assertEqual(self.sockets, [])
        self.page.close()

    def test_real_vectors_match_neutral_and_comparison_can_be_inspected_on_mobile(self):
        self.assertTrue(self.page.locator("#artContent").is_visible())
        self.assertEqual(self.page.locator("#artPose option").count(), 7)
        pixels = self.page.evaluate("""async () => {
          async function render(variant) {
            const image = new Image();
            image.src=`./assets/overlap-candidates/poses/neutral-${variant}.svg`;
            await image.decode();
            const canvas=document.createElement('canvas'); canvas.width=1024;canvas.height=1024;
            const context=canvas.getContext('2d');
            // Preserve the source aspect and the preparation PSD margins.
            const scale=896/337, width=270*scale;
            context.drawImage(image,(1024-width)/2,64,width,896);
            return context.getImageData(0,0,1024,1024).data;
          }
          const original=await render('original'),candidate=await render('candidate');
          return {equal:original.every((value,index)=>value===candidate[index]),
                  drawn:original.filter((value,index)=>index%4===3 && value>0).length};
        }""")
        self.assertTrue(pixels["equal"])
        self.assertGreater(pixels["drawn"], 200000)
        self.page.locator("#artPose").select_option("combined")
        self.assertEqual(
            self.page.locator("#candidateArt").get_attribute("data-pose"), "combined"
        )
        self.page.locator('[data-art-view="shoulder"]').click()
        self.assertEqual(
            self.page.locator("#originalArt").get_attribute("viewBox"),
            "218 495 200 105",
        )
        bounds = self.page.locator("#originalArt").bounding_box()
        self.assertAlmostEqual(bounds["height"] / bounds["width"], 105 / 200, places=2)
        self.page.locator("#artGuide").check()
        self.assertEqual(self.page.locator("[data-joint-guide]:visible").count(), 2)
        self.page.locator("#artPose").select_option("stress")
        self.assertIn("범위 밖", self.page.locator("#artPoseNote").inner_text())
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.assertFalse(
            self.page.evaluate("document.documentElement.scrollWidth>innerWidth")
        )
        output = Path("tmp/sogangi-browser/art-review")
        output.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(output / "shoulders-mobile.png"), full_page=True)
        self.page.set_viewport_size({"width": 1440, "height": 1100})
        self.page.locator("#artPose").select_option("greet-peak")
        self.page.locator('[data-art-view="full"]').click()
        self.page.locator("#artGuide").uncheck()
        self.page.screenshot(path=str(output / "greeting-desktop.png"), full_page=True)

    def test_download_keeps_baseline_and_candidate_provenance_separate(self):
        baseline = self.page.request.get(
            self.root + "assets/production/handoff-manifest.json"
        ).json()
        review = self.page.request.get(
            self.root + "assets/overlap-candidates/review.json"
        ).json()
        self.assertEqual(review["baseline_psd_sha256"], baseline["psd_sha256"])
        self.assertFalse(review["official_artwork"])
        self.assertFalse(review["cubism_import_verified"])
        self.assertTrue(review["verification"]["baseline_layers_unchanged"])
        with self.page.expect_download() as event:
            self.page.locator('a[download][href$="candidate.zip"]').click()
        download = event.value
        with zipfile.ZipFile(download.path()) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), len(set(names)))
            self.assertFalse(any(".." in name.split("/") for name in names))
            manifest = json.loads(archive.read("review.json"))
            psd = archive.read("sogangi-shoulder-candidate.psd")
            self.assertEqual(psd[:6], b"8BPS\x00\x01")
            self.assertEqual(
                hashlib.sha256(psd).hexdigest(), review["candidate_psd_sha256"]
            )
            self.assertEqual(manifest["layer_count"], 26)
            self.assertEqual(
                sum(part["authored_candidate"] for part in manifest["parts"]), 2
            )
            self.assertEqual(
                len([name for name in names if name.startswith("layers/")]), 26
            )
        # Loading the candidate never rewrites the official-preparation download.
        original = self.page.request.get(
            self.root + "assets/production/sogangi-visible-parts.psd"
        ).body()
        self.assertEqual(hashlib.sha256(original).hexdigest(), baseline["psd_sha256"])

    def test_rendered_eye_and_mouth_do_not_jump_at_the_old_switch_thresholds(self):
        self.page.goto(self.root + "live2d-plan.html", wait_until="networkidle")
        self.page.wait_for_function("!document.querySelector('#poseMouth').disabled")
        results = self.page.evaluate("""async () => {
          async function pixels(selector, amount, crop) {
            const input=document.querySelector(selector);
            input.value=amount;input.dispatchEvent(new Event('input',{bubbles:true}));
            const svg=document.querySelector('#motionPreview').cloneNode(true);
            svg.setAttribute('viewBox',crop); svg.setAttribute('width','600');svg.setAttribute('height','380');
            const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml'}));
            try {
              const image=new Image();image.src=url;await image.decode();
              const canvas=document.createElement('canvas');canvas.width=600;canvas.height=380;
              const context=canvas.getContext('2d');context.drawImage(image,0,0,600,380);
              return context.getImageData(0,0,600,380).data;
            } finally {URL.revokeObjectURL(url);}
          }
          function distance(a,b) {let sum=0;for(let i=0;i<a.length;i++)sum+=Math.abs(a[i]-b[i]);return sum;}
          const results=[];
          for (const [selector,values,crop] of [
            ['#poseMouth',[0,.11,.12,.13,1],'280 476 60 38'],
            ['#poseLeft',[0,.15,.16,.17,1],'243 420 54 54']
          ]) {
            const frames=[];for(const value of values)frames.push(await pixels(selector,value,crop));
            const total=distance(frames[0],frames[4]);
            results.push({selector,total,nearby:[distance(frames[1],frames[2])/total,distance(frames[2],frames[3])/total]});
          }
          return results;
        }""")
        for result in results:
            self.assertGreater(result["total"], 10000, result)
            self.assertLess(max(result["nearby"]), 0.08, result)

    def test_grouped_import_download_preserves_paths_pixels_and_keyform_targets(self):
        self.page.goto(self.root + "live2d-plan.html", wait_until="networkidle")
        with self.page.expect_download() as event:
            self.page.locator("#downloadImportArt").click()
        with zipfile.ZipFile(event.value.path()) as archive:
            manifest = json.loads(archive.read("import-manifest.json"))
            plan = json.loads(archive.read("keyform-plan.json"))
            psd = archive.read("sogangi-cubism-import.psd")
            self.assertEqual(psd[:6], b"8BPS\x00\x01")
            self.assertEqual(hashlib.sha256(psd).hexdigest(), manifest["psd_sha256"])
            self.assertEqual(manifest["group_count"], 9)
            self.assertEqual(manifest["layer_count"], 24)
            self.assertTrue(manifest["verification"]["layer_pixels_and_offsets_exact"])
            self.assertFalse(manifest["editor_import_verified"])
            paths = {tuple(part["path"]) for part in manifest["parts"]}
            by_path = {tuple(part["path"]): part for part in manifest["parts"]}
            self.assertEqual(len(paths), 24)
            self.assertEqual(sum(not part["visible"] for part in manifest["parts"]), 3)
            self.assertEqual(
                [parameter["id"] for parameter in plan["parameters"]],
                ["ParamEyeLOpen", "ParamEyeROpen", "ParamMouthOpenY"],
            )
            for parameter in plan["parameters"]:
                for target in parameter["targets"]:
                    self.assertIn(tuple(target["path"]), paths)
                    default = next(
                        state
                        for state in target["states"]
                        if state["value"] == parameter["default"]
                    )
                    self.assertEqual(
                        default["opacity"],
                        int(by_path[tuple(target["path"])]["visible"]),
                    )
                    self.assertTrue(
                        all(0 <= value <= 2048 for value in target["pivot_psd"])
                    )
            atlas = json.loads(archive.read("atlas-layout-proposal.json"))
            self.assertEqual(atlas["status"], "placement_proposal_not_editor_export")
            self.assertEqual((atlas["width"], atlas["height"]), (2048, 2048))
            self.assertEqual(
                {part["name"] for part in atlas["placements"]},
                {part["name"] for part in manifest["parts"]},
            )
            boxes = [part["allocation"] for part in atlas["placements"]]
            for index, (x, y, width, height) in enumerate(boxes):
                self.assertTrue(
                    x >= 0 and y >= 0 and x + width <= 2048 and y + height <= 2048
                )
                for ox, oy, ow, oh in boxes[index + 1 :]:
                    self.assertTrue(
                        x + width <= ox
                        or ox + ow <= x
                        or y + height <= oy
                        or oy + oh <= y
                    )
            independent = self.page.request.get(
                self.root + "assets/cubism-import/independent-reader-report.json"
            ).json()
            self.assertEqual(independent["psd_sha256"], manifest["psd_sha256"])
            self.assertTrue(independent["layer_pixels_exact"])
            self.assertFalse(independent["editor_import_verified"])
            self.assertFalse(independent["auto_inference_approved"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
