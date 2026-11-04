"""Actual composed MOC keyforms: face controls survive tilt/breath, no model API."""

import json
from pathlib import Path
import unittest

from live2d_preview import Live2DPreviewTests


class SogangiMotionTests(Live2DPreviewTests):
    # Reuse setup/helpers; the explicit suite below runs only this new case.
    def test_greeting_arm_stays_attached_and_composes_with_other_controls(self):
        self.page.locator("#loadSogangiMotion").click()
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.loaded==='true'"
        )
        self.page.wait_for_timeout(100)
        self.snapshot(reference=True)
        self.page.locator("#loadSogangiGreeting").click()
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.modelUrl.includes('sogangi-greeting')"
        )
        self.page.wait_for_timeout(100)
        self.assertEqual(self.snapshot()["different"], 0)
        neutral_components = self.large_components()
        output = Path("tmp/sogangi-browser/greeting")
        output.mkdir(parents=True, exist_ok=True)
        for breath in [0, 1]:
            for wave in [0, 0.125, 0.25, 0.5, 0.75, 1]:
                self.set_pose(wave=wave, breath=breath)
                self.assertEqual(
                    self.large_components(), neutral_components, (wave, breath)
                )
                values = json.loads(
                    self.page.locator("#modelStage").get_attribute(
                        "data-applied-parameters"
                    )
                )
                self.assertEqual(values["ParamArmRWave"], wave)
                if wave == 1:
                    self.page.screenshot(
                        path=str(output / f"arm-max-breath-{breath}.png"),
                        full_page=True,
                    )
        self.set_pose(wave=1, breath=1, tilt=-30, mouth=1, eyeL=0, eyeR=0)
        self.assertEqual(self.large_components(), neutral_components)
        self.page.screenshot(path=str(output / "combined.png"), full_page=True)
        self.page.locator("#resetPose").click()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.snapshot()["different"], 0)
        self.page.screenshot(path=str(output / "neutral.png"), full_page=True)

    def large_components(self):
        return self.page.evaluate("""()=>{
          const source=document.querySelector('#modelCanvas'),canvas=document.createElement('canvas');
          canvas.width=source.width;canvas.height=source.height;
          const context=canvas.getContext('2d');context.drawImage(source,0,0);
          const w=canvas.width,h=canvas.height,p=context.getImageData(0,0,w,h).data;
          const seen=new Uint8Array(w*h),stack=new Int32Array(w*h);let large=0;
          for(let index=0;index<w*h;index++){
            if(seen[index]||p[index*4+3]<32)continue;
            let size=0,top=0;seen[index]=1;stack[top++]=index;
            while(top){const at=stack[--top];size++;
              for(const next of [at%w?at-1:-1,at%w<w-1?at+1:-1,at-w,at+w]){
                if(next<0||next>=w*h||seen[next]||p[next*4+3]<32)continue;
                seen[next]=1;stack[top++]=next;
              }
            }
            if(size>20)large++;
          }
          return large;
        }""")

    def test_motion_grid_preserves_neutral_and_composes_eyes_and_mouth(self):
        self.page.locator("#loadSogangi").click()
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.loaded==='true'"
        )
        self.page.wait_for_timeout(100)
        self.snapshot(reference=True)
        self.page.locator("#loadSogangiMotion").click()
        self.page.wait_for_function(
            "document.querySelector('#modelStage').dataset.modelUrl.includes('sogangi-motion')"
        )
        self.page.wait_for_timeout(100)
        self.assertEqual(self.snapshot()["different"], 0, "Neutral artwork changed")
        self.assertFalse(self.page.locator("#parameter-tilt").is_disabled())
        self.assertFalse(self.page.locator("#parameter-breath").is_disabled())
        self.set_pose(tilt=30, breath=1)
        self.assertGreater(self.snapshot()["different"], 1000)
        self.snapshot(pose_reference=True)
        self.set_pose(mouth=1)
        self.assertGreater(self.snapshot()["pose_difference"], 100)
        self.set_pose(eyeL=0, eyeR=0)
        output = Path("tmp/sogangi-browser/motion")
        output.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(output / "combined.png"), full_page=True)
        self.assertGreater(self.snapshot()["drawn"], 10000)
        for tilt, breath in [(-30, 0), (-15, 0.5), (0, 1), (15, 0.5), (30, 1)]:
            self.set_pose(tilt=tilt, breath=breath, eyeL=1, eyeR=1, mouth=0)
            self.snapshot(pose_reference=True)
            self.set_pose(mouth=0.5, eyeL=0, eyeR=0)
            self.assertGreater(self.snapshot()["pose_difference"], 100)
            self.assertGreater(self.snapshot()["drawn"], 10000)
            values = json.loads(
                self.page.locator("#modelStage").get_attribute(
                    "data-applied-parameters"
                )
            )
            self.assertEqual(values["ParamAngleZ"], tilt)
            self.assertEqual(values["ParamBreath"], breath)
            self.assertEqual(values["ParamMouthOpenY"], 0.5)
            self.assertEqual(values["ParamEyeLOpen"], 0)
        self.page.locator("#resetPose").click()
        self.page.wait_for_timeout(100)
        self.assertEqual(self.snapshot()["different"], 0)
        self.page.screenshot(path=str(output / "neutral.png"), full_page=True)

    def set_pose(self, **values):
        frame = int(self.page.locator("#modelStage").get_attribute("data-frames"))
        for name, value in values.items():
            self.page.locator("#parameter-" + name).evaluate(
                "(input,value)=>{input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}))}",
                value,
            )
        self.page.wait_for_function(
            "frame=>Number(document.querySelector('#modelStage').dataset.frames)>frame+2",
            arg=frame,
        )

    def snapshot(self, reference=False, pose_reference=False):
        return self.page.evaluate(
            """([reference,poseReference])=>{
              const canvas=document.querySelector('#modelCanvas'),copy=document.createElement('canvas');
              copy.width=canvas.width;copy.height=canvas.height;
              const context=copy.getContext('2d');context.drawImage(canvas,0,0);
              const pixels=context.getImageData(0,0,copy.width,copy.height).data;
              if(reference)window.__motionNeutral=pixels;
              if(poseReference)window.__motionPose=pixels;
              const difference=reference=>reference?pixels.filter((v,i)=>v!==reference[i]).length:0;
              return {drawn:pixels.filter((v,i)=>i%4===3&&v>0).length,
                different:difference(window.__motionNeutral),pose_difference:difference(window.__motionPose)};
            }""",
            [reference, pose_reference],
        )


if __name__ == "__main__":
    suite = unittest.TestSuite(
        [
            SogangiMotionTests(
                "test_motion_grid_preserves_neutral_and_composes_eyes_and_mouth"
            ),
            SogangiMotionTests(
                "test_greeting_arm_stays_attached_and_composes_with_other_controls"
            ),
        ]
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
