"""Real MOC/Core in the chat page with fixture messages and real HTML audio clocks.

No model/TTS service calls. Tests isolate the renderer while retaining the app's
actual audio queue, request correlation, persistence and interruption handlers.
"""

import os
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright
from sogangi_smoke import SogangiBrowserCase, wav_fixture


class Live2DChatTests(SogangiBrowserCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=os.environ.get(
                "SOGANGI_BROWSER",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            ),
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--enable-unsafe-swiftshader",
            ],
        )

    def select_mode(self, mode, wait=True):
        self.page.locator("#settingsButton").click()
        self.page.locator("#avatarInput").select_option(mode)
        self.page.locator("#settingsClose").click()
        if wait:
            self.wait_mode(mode)

    def wait_mode(self, mode):
        renderer = "live2d" if mode == "live2d" else "svg-parts"
        self.page.wait_for_function(
            "renderer=>document.querySelector('#mascot').dataset.renderer===renderer",
            arg=renderer,
            timeout=30000,
        )
        if mode == "live2d":
            self.page.wait_for_function(
                "Number(document.querySelector('#avatarCanvas').dataset.frames)>3"
            )

    def freeze_secondary_motion(self):
        self.page.locator("#settingsButton").click()
        self.page.locator("#reducedMotionInput").check()
        self.page.locator("#settingsClose").click()

    def start_audio(self, seconds=2, expression="neutral"):
        self.submit("실제 모델의 음성 제어 시험")
        self.fixture.turn_message(
            "text-response", display_text={"text": "확인 중이야."}
        )
        self.fixture.turn_message(
            "audio",
            display_text={"text": f"[{expression}] 확인 중이야."},
            audio=wav_fixture(seconds),
            volumes=[0.75] * int(seconds * 50),
            slice_length=20,
        )
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedMouth)>.5"
        )

    def assert_closed(self):
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedMouth)===0"
        )
        self.page.wait_for_timeout(120)
        self.assertEqual(
            self.page.locator("#avatarCanvas").get_attribute("data-applied-mouth"), "0"
        )

    def pixels(self, reference=False):
        return self.page.evaluate(
            """reference=>{
          const source=document.querySelector('#avatarCanvas'),canvas=document.createElement('canvas');
          canvas.width=source.width;canvas.height=source.height;
          const context=canvas.getContext('2d');context.drawImage(source,0,0);
          const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
          if(reference)window.__avatarReference=pixels;
          return {drawn:pixels.filter((v,i)=>i%4===3&&v>0).length,
                  difference:window.__avatarReference?pixels.filter((v,i)=>v!==window.__avatarReference[i]).length:0};
        }""",
            reference,
        )

    def test_actual_audio_clock_controls_native_mouth_and_restores_pixels(self):
        self.select_mode("live2d")
        self.freeze_secondary_motion()
        self.assertFalse(self.page.locator("#greetButton").is_disabled())
        self.assertGreater(self.pixels(True)["drawn"], 10000)
        self.start_audio(seconds=1)
        self.assertGreater(self.pixels()["difference"], 100)
        output = Path("tmp/sogangi-browser/live2d-chat")
        output.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(output / "speaking-desktop.png"), full_page=True)
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.assert_closed()
        self.assertEqual(self.pixels()["difference"], 0)
        self.assertEqual(
            sum(
                item["type"] == "frontend-playback-complete"
                for item in self.fixture.received
            ),
            1,
        )
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.wait_for_timeout(100)
        self.assertFalse(
            self.page.evaluate("document.documentElement.scrollWidth>innerWidth")
        )
        self.assertGreater(self.pixels()["drawn"], 1000)
        self.page.screenshot(path=str(output / "mobile.png"), full_page=True)

    def test_stop_and_new_chat_reject_late_native_audio(self):
        self.select_mode("live2d")
        self.start_audio()
        request_id = self.fixture.current_request
        self.page.locator("#stopButton").click()
        self.wait_ready()
        self.assert_closed()
        self.page.locator("#newChat").click()
        self.wait_ready()
        self.fixture.send(
            {
                "type": "audio",
                "request_id": request_id,
                "audio": wav_fixture(1),
                "display_text": {"text": "[joy] 지난 답변"},
                "volumes": [1] * 50,
                "slice_length": 20,
            }
        )
        self.page.wait_for_timeout(200)
        self.assert_closed()
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "neutral"
        )

    def test_mute_closes_native_mouth_without_late_reopening(self):
        self.select_mode("live2d")
        self.start_audio()
        self.fixture.turn_message("backend-synth-complete")
        self.page.locator("#soundToggle").click()
        self.wait_ready()
        self.assert_closed()
        self.page.wait_for_timeout(250)
        self.assert_closed()

    def test_native_head_and_breath_freeze_without_disabling_audio_lip_sync(self):
        self.select_mode("live2d")
        stage = self.page.locator(".stage").bounding_box()
        self.page.mouse.move(
            stage["x"] + stage["width"] * 0.99, stage["y"] + stage["height"] * 0.5
        )
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedHead)>23"
        )
        self.assertEqual(
            self.page.evaluate("""()=>{
          const source=document.querySelector('#avatarCanvas'),canvas=document.createElement('canvas');
          canvas.width=source.width;canvas.height=source.height;
          const context=canvas.getContext('2d');context.drawImage(source,0,0);
          const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
          let edge=0;
          for(let y=0;y<canvas.height;y++)for(const x of [0,canvas.width-1])
            if(pixels[(y*canvas.width+x)*4+3]>0)edge++;
          for(let x=0;x<canvas.width;x++)for(const y of [0,canvas.height-1])
            if(pixels[(y*canvas.width+x)*4+3]>0)edge++;
          return edge;
        }"""),
            0,
            "Tilted artwork touches the canvas edge",
        )
        first = float(
            self.page.locator("#avatarCanvas").get_attribute("data-applied-breath")
        )
        self.page.wait_for_function(
            "first=>Math.abs(Number(document.querySelector('#avatarCanvas').dataset.appliedBreath)-first)>.03",
            arg=first,
            timeout=3000,
        )
        self.page.mouse.move(1, 1)
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedHead)===0"
        )
        self.freeze_secondary_motion()
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedBreath)===0"
        )
        self.pixels(True)
        self.page.wait_for_timeout(200)
        self.assertEqual(self.pixels()["difference"], 0)
        self.page.emulate_media(reduced_motion="reduce")
        self.page.locator("#settingsButton").click()
        self.page.locator("#reducedMotionInput").uncheck()
        self.page.locator("#settingsClose").click()
        # OS-level reduction still freezes the new movement with app reduction off.
        self.page.wait_for_timeout(100)
        self.start_audio(seconds=1)
        self.assertEqual(
            self.page.locator("#avatarCanvas").get_attribute("data-applied-head"), "0"
        )
        self.assertEqual(
            self.page.locator("#avatarCanvas").get_attribute("data-applied-breath"), "0"
        )
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.assert_closed()
        self.assertEqual(self.pixels()["difference"], 0)

    def wait_arm_active(self):
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedArm)>.15"
        )

    def assert_arm_closed(self):
        self.page.wait_for_function(
            "document.querySelector('#avatarCanvas').dataset.appliedArm==='0' && document.querySelector('#mascot').dataset.greeting==='false'"
        )

    def test_native_greeting_finishes_once_without_calling_chat(self):
        self.select_mode("live2d")
        self.page.locator("#greetButton").click()
        self.wait_arm_active()
        output = Path("tmp/sogangi-browser/greeting")
        output.mkdir(parents=True, exist_ok=True)
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedArm)>.65"
        )
        self.page.screenshot(path=str(output / "chat-greeting.png"), full_page=True)
        self.page.wait_for_timeout(500)
        self.page.locator("#greetButton").click()
        self.page.wait_for_function(
            "document.querySelector('#avatarCanvas').dataset.appliedArm==='0' && document.querySelector('#mascot').dataset.greeting==='false'",
            timeout=1100,
        )
        self.page.wait_for_timeout(150)
        self.assert_arm_closed()
        self.assertEqual(
            sum(item["type"] == "text-input" for item in self.fixture.received), 0
        )

    def test_native_greeting_cancels_on_reduce_stop_new_chat_and_mode_switch(self):
        self.select_mode("live2d")
        self.page.locator("#greetButton").click()
        self.wait_arm_active()
        self.freeze_secondary_motion()
        self.assert_arm_closed()
        self.page.locator("#settingsButton").click()
        self.page.locator("#reducedMotionInput").uncheck()
        self.page.locator("#settingsClose").click()
        self.page.wait_for_timeout(150)
        self.assert_arm_closed()
        self.page.locator("#greetButton").click()
        self.wait_arm_active()
        self.page.locator("#soundToggle").click()
        self.assert_arm_closed()
        self.page.locator("#soundToggle").click()
        self.assert_arm_closed()
        self.start_audio(seconds=2)
        self.page.locator("#greetButton").click()
        self.wait_arm_active()
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedMouth)>.5"
        )
        self.page.locator("#stopButton").click()
        self.wait_ready()
        self.assert_arm_closed()
        self.assert_closed()
        self.page.locator("#greetButton").click()
        self.wait_arm_active()
        self.page.locator("#newChat").click()
        self.wait_ready()
        self.assert_arm_closed()
        self.page.locator("#greetButton").click()
        self.wait_arm_active()
        self.select_mode("svg")
        self.select_mode("live2d")
        self.assert_arm_closed()
        self.page.emulate_media(reduced_motion="reduce")
        self.page.locator("#greetButton").click()
        self.page.wait_for_timeout(200)
        self.assert_arm_closed()
        self.page.emulate_media(reduced_motion="no-preference")
        self.page.wait_for_timeout(150)
        self.assert_arm_closed()
        self.assertEqual(
            sum(item["type"] == "text-input" for item in self.fixture.received), 1
        )

    def test_sentence_expression_drives_native_eyes_and_muted_text_keeps_mouth_closed(
        self,
    ):
        self.select_mode("live2d")
        self.start_audio(seconds=1, expression="joy")
        self.page.wait_for_function(
            "document.querySelector('#avatarCanvas').dataset.appliedEyes==='0.00,0.00'"
        )
        self.fixture.turn_message(
            "text-response", display_text={"text": "[neutral] 다음 문장이야."}
        )
        self.fixture.turn_message(
            "audio",
            display_text={"text": "[neutral] 다음 문장이야."},
            audio=wav_fixture(1),
            volumes=[0.4] * 50,
            slice_length=20,
        )
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "joy"
        )
        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.expression==='neutral'"
        )
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.assert_closed()
        self.page.locator("#soundToggle").click()
        self.submit("음소거 중 기쁜 표정")
        self.finish("[joy] 반가워!", audio=wav_fixture(0.2))
        self.page.wait_for_function(
            "document.querySelector('#avatarCanvas').dataset.appliedEyes==='0.00,0.00'"
        )
        self.assert_closed()

    def wait_mood(self, value):
        self.page.wait_for_function(
            "value=>Number(document.querySelector('#avatarCanvas').dataset.appliedMood)===value",
            arg=value,
        )

    def test_anger_surprise_follow_playing_sentence_and_muted_tags(self):
        self.select_mode("live2d")
        self.start_audio(seconds=1.4, expression="anger")
        self.wait_mood(1)
        self.fixture.turn_message(
            "text-response", display_text={"text": "[SURPRISE] 다음 문장이야."}
        )
        self.fixture.turn_message(
            "audio",
            display_text={"text": "[SURPRISE] 다음 문장이야."},
            audio=wav_fixture(1),
            volumes=[0.5] * 50,
            slice_length=20,
        )
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "anger"
        )
        self.wait_mood(2)
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.assert_closed()
        self.page.locator("#soundToggle").click()
        self.submit("음소거 중 화난 표정 확인")
        self.finish("[anger] 잠깐만!", audio=wav_fixture(0.2))
        self.wait_mood(1)
        self.assert_closed()
        self.page.locator("#newChat").click()
        self.wait_ready()
        self.wait_mood(0)
        self.submit("준비되지 않은 표정 확인")
        self.finish("[fear] 확인 중이야.", audio=wav_fixture(0.2))
        self.wait_mood(2)
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "surprise"
        )

    def test_emotion_survives_renderer_fallback_and_reduction_but_not_interruption(
        self,
    ):
        self.select_mode("live2d")
        self.start_audio(seconds=3, expression="anger")
        self.wait_mood(1)
        old_request = self.fixture.current_request
        self.select_mode("svg")
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "neutral"
        )
        self.select_mode("live2d")
        self.wait_mood(1)
        self.page.locator("#stopButton").click()
        self.wait_ready()
        self.wait_mood(0)
        self.fixture.send(
            {
                "type": "audio",
                "request_id": old_request,
                "display_text": {"text": "[surprise] 이전 답변"},
                "audio": wav_fixture(0.2),
                "volumes": [1] * 10,
                "slice_length": 20,
            }
        )
        self.page.wait_for_timeout(200)
        self.wait_mood(0)
        self.assert_closed()
        self.freeze_secondary_motion()
        self.page.locator("#soundToggle").click()
        self.submit("움직임을 줄인 상태에서도 놀란 표정")
        self.finish("[surprise] 발견했어!", audio=wav_fixture(0.2))
        self.wait_mood(2)
        self.assert_closed()
        self.page.wait_for_timeout(200)
        self.assertEqual(
            self.page.locator("#avatarCanvas").get_attribute("data-applied-head"), "0"
        )
        self.assertEqual(
            self.page.locator("#avatarCanvas").get_attribute("data-applied-breath"), "0"
        )

    def test_switching_during_audio_keeps_clock_and_does_not_repeat_requests(self):
        self.select_mode("live2d")
        self.page.evaluate("""()=>{window.__avatarAudio=[];const play=HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play=function(...args){window.__avatarAudio.push(this);return play.apply(this,args);};}""")
        self.start_audio(seconds=4)
        self.page.locator("#messageInput").fill("작성 중인 다음 질문")
        time_before = self.page.evaluate("window.__avatarAudio[0].currentTime")
        self.page.evaluate(
            "window.__oldAvatarCanvas=document.querySelector('#avatarCanvas')"
        )
        self.select_mode("svg")
        self.assertGreater(
            self.page.evaluate("window.__avatarAudio[0].currentTime"), time_before
        )
        old_frames = self.page.evaluate("window.__oldAvatarCanvas.dataset.frames")
        self.select_mode("live2d")
        self.page.wait_for_function(
            "Number(document.querySelector('#avatarCanvas').dataset.appliedMouth)>.5"
        )
        self.assertEqual(
            self.page.evaluate("window.__oldAvatarCanvas.dataset.frames"), old_frames
        )
        self.assertEqual(self.page.evaluate("window.__avatarAudio.length"), 1)
        self.assertEqual(
            self.page.locator("#messageInput").input_value(), "작성 중인 다음 질문"
        )
        self.assertEqual(
            sum(item["type"] == "text-input" for item in self.fixture.received), 1
        )
        self.assertEqual(
            sum(item["type"] == "switch-config" for item in self.fixture.received), 1
        )
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.assert_closed()

    def test_late_model_load_does_not_replay_a_finished_mouth_animation(self):
        moc = self.page.request.get(
            os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
            + "/live2d-models/sogangi-expressions/runtime/sogangi.moc3"
        ).body()
        pending = []
        self.page.route("**/sogangi.moc3?*", lambda route: pending.append(route))
        self.select_mode("live2d", wait=False)
        for _ in range(200):
            if pending:
                break
            self.page.wait_for_timeout(50)
        self.assertEqual(len(pending), 1)
        self.submit("불러오는 동안의 질문")
        self.fixture.turn_message(
            "text-response", display_text={"text": "짧은 답변이야."}
        )
        self.fixture.turn_message(
            "audio",
            display_text={"text": "짧은 답변이야."},
            audio=wav_fixture(0.2),
            volumes=[0.8] * 10,
            slice_length=20,
        )
        self.page.wait_for_function(
            "Number(document.querySelector('#mascot').dataset.mouthOpen)>.5"
        )
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        pending[0].fulfill(
            status=200, content_type="application/octet-stream", body=moc
        )
        self.wait_mode("live2d")
        self.assert_closed()
        self.page.wait_for_timeout(200)
        self.assert_closed()

    def test_bad_model_reference_falls_back_and_retry_keeps_the_conversation(self):
        self.page.locator("#messageInput").fill("유지할 초안")
        requests = []
        self.page.on("request", lambda request: requests.append(request.url))
        pattern = "**/sogangi-expressions/runtime/sogangi.model3.json"
        self.page.route(
            pattern,
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"Version":3,"FileReferences":{"Moc":"../../conf.yaml","Textures":["textures/texture_00.png"]}}',
            ),
        )
        self.select_mode("live2d", wait=False)
        self.page.wait_for_function("!document.querySelector('#avatarRetry').hidden")
        self.wait_mode("svg")
        self.assertFalse(any(url.endswith("/conf.yaml") for url in requests))
        self.page.unroute(pattern)
        self.page.locator("#settingsButton").click()
        self.page.locator("#avatarRetry").click()
        self.page.locator("#settingsClose").click()
        self.wait_mode("live2d")
        self.assertEqual(
            self.page.locator("#messageInput").input_value(), "유지할 초안"
        )
        self.assertEqual(self.fixture.history, 1)

    def test_context_loss_recovers_and_saved_mode_resumes_after_refresh(self):
        # No saved choice and no URL override: the normal page defaults to MOC3.
        self.page.evaluate("localStorage.removeItem('sogangi.preferences.v1')")
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()
        self.wait_mode("live2d")
        self.page.locator("#settingsButton").click()
        self.assertEqual(self.page.locator("#avatarInput").input_value(), "live2d")
        self.page.locator("#settingsClose").click()
        self.select_mode("svg")
        root = self.page.url.split("?")[0]
        self.page.goto(root + "?avatar=live2d", wait_until="domcontentloaded")
        self.wait_ready()
        self.wait_mode("live2d")
        self.page.goto(root, wait_until="domcontentloaded")
        self.wait_ready()
        self.wait_mode("live2d")
        self.assertEqual(
            self.page.evaluate(
                "JSON.parse(localStorage.getItem('sogangi.preferences.v1')).avatarRenderer"
            ),
            "live2d",
        )
        self.page.locator("#avatarCanvas").dispatch_event("webglcontextlost")
        self.wait_mode("svg")
        self.page.locator("#settingsButton").click()
        self.page.locator("#avatarRetry").click()
        self.page.locator("#settingsClose").click()
        self.wait_mode("live2d")
        self.assertGreater(self.pixels()["drawn"], 10000)
        self.page.locator("#messageInput").fill("새로고침 후에도 남을 초안")
        self.page.locator("#messageInput").dispatch_event("input")
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()
        self.wait_mode("live2d")
        self.assertEqual(
            self.page.locator("#messageInput").input_value(),
            "새로고침 후에도 남을 초안",
        )
        self.assertEqual(self.fixture.history, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
