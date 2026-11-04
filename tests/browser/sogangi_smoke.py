"""Browser regressions against the real UI with a local WebSocket fixture, no LLM calls.

Run with the optional Playwright environment described in README.md.
"""

import base64
import io
import json
import os
from pathlib import Path
import unittest
import wave

from playwright.sync_api import sync_playwright


def wav_fixture(seconds=0.2):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * int(16000 * seconds))
    return base64.b64encode(buffer.getvalue()).decode()


class ChatFixture:
    def __init__(self):
        self.received = []
        self.route = None
        self.history = 0
        self.current_request = None
        self.histories = {}
        self.active_uid = None
        self.history_items = None

    def send(self, message):
        self.route.send(json.dumps(message))

    def connect(self, route):
        self.route = route
        route.on_message(self.receive)
        self.send(
            {"type": "set-model-and-conf", "conf_uid": "default", "model_info": {}}
        )

    def receive(self, raw):
        message = json.loads(raw)
        self.received.append(message)
        if message["type"] == "switch-config":
            self.send({"type": "config-switched"})
        elif message["type"] == "create-new-history":
            self.history += 1
            self.active_uid = f"fixture-{self.history}"
            self.histories[self.active_uid] = []
            self.send(
                {
                    "type": "new-history-created",
                    "history_uid": f"fixture-{self.history}",
                }
            )
        elif message["type"] == "text-input":
            self.current_request = message["request_id"]
            self.histories.setdefault(self.active_uid, []).append(
                {"role": "human", "content": message["text"]}
            )
        elif message["type"] == "fetch-history-list":
            if self.history_items is not None:
                self.send({"type": "history-list", "histories": self.history_items})
                return
            self.send(
                {
                    "type": "history-list",
                    "histories": [
                        {
                            "uid": "saved-fixture",
                            "timestamp": "2026-10-30T00:00:00",
                            "latest_message": {"content": "저장된 시험 대화"},
                        }
                    ],
                }
            )
        elif message["type"] == "fetch-and-set-history":
            if message["history_uid"] != "saved-fixture":
                uid = message["history_uid"]
                if uid not in self.histories:
                    self.send(
                        {
                            "type": "history-error",
                            "operation": "fetch",
                            "history_uid": uid,
                            "code": "unavailable",
                        }
                    )
                else:
                    self.active_uid = uid
                    self.send(
                        {
                            "type": "history-data",
                            "history_uid": uid,
                            "messages": self.histories[uid],
                        }
                    )
                return
            self.active_uid = "saved-fixture"
            self.histories.setdefault("saved-fixture", [])
            self.send(
                {
                    "type": "history-data",
                    "messages": [
                        {"role": "metadata"},
                        {"role": "human", "content": "[neutral]도 원래 입력 그대로"},
                        {"role": "ai", "content": "[joy] 기억을 불러왔어!"},
                    ],
                }
            )
        elif message["type"] == "frontend-playback-complete":
            self.send(
                {
                    "type": "control",
                    "text": "conversation-chain-end",
                    "request_id": self.current_request,
                }
            )

    def turn_message(self, kind, **kwargs):
        if kind == "text-response" and kwargs.get("display_text", {}).get("text"):
            self.histories.setdefault(self.active_uid, []).append(
                {"role": "ai", "content": kwargs["display_text"]["text"]}
            )
        self.send({"type": kind, "request_id": self.current_request, **kwargs})


class SogangiBrowserCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        executable = os.environ.get(
            "SOGANGI_BROWSER", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        cls.browser = cls.playwright.chromium.launch(
            executable_path=executable,
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
            ],
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        base_url = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
        # These regressions explicitly exercise the SVG renderer. Keep that
        # preference in storage so reloads still test the user's saved choice.
        self.page = self.browser.new_page(
            viewport={"width": 1280, "height": 900},
            storage_state={
                "cookies": [],
                "origins": [
                    {
                        "origin": base_url.rstrip("/"),
                        "localStorage": [
                            {
                                "name": "sogangi.preferences.v1",
                                "value": json.dumps({"avatarRenderer": "svg"}),
                            }
                        ],
                    }
                ],
            },
        )
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.fixture = ChatFixture()
        self.page.route_web_socket("**/client-ws", self.fixture.connect)
        self.page.goto(
            base_url + "/web-tool/sogangi/",
            wait_until="domcontentloaded",
        )
        self.wait_ready()

        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.renderer==='svg-parts'"
        )

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.page.close()

    def wait_ready(self):
        self.page.wait_for_function(
            "document.querySelector('#connection').textContent==='연결됨' && !document.querySelector('#sendButton').disabled",
            timeout=10000,
        )

    def submit(self, text):
        self.page.locator("#messageInput").fill(text)
        self.page.locator("#sendButton").click()
        self.page.wait_for_timeout(30)

    def finish(self, text="안녕, 서강이야!", audio=None):
        self.fixture.turn_message("text-response", display_text={"text": text})
        self.fixture.turn_message("audio", display_text={"text": text}, audio=audio)
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()


class SogangiBrowserTests(SogangiBrowserCase):
    def test_expression_follows_playing_sentence_not_early_next_text(self):
        self.submit("문장별 표정 시험")
        self.fixture.turn_message(
            "text-response", display_text={"text": "[joy] 반가워!"}
        )
        self.fixture.turn_message(
            "audio",
            display_text={"text": "[joy] 반가워!"},
            audio=wav_fixture(1),
            volumes=[0.7] * 50,
            slice_length=20,
        )
        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.expression==='joy'"
        )
        self.fixture.turn_message(
            "text-response", display_text={"text": "[neutral] 다음 문장이야."}
        )
        self.fixture.turn_message(
            "audio",
            display_text={"text": "[neutral] 다음 문장이야."},
            audio=wav_fixture(1),
            volumes=[0.5] * 50,
            slice_length=20,
        )
        self.page.wait_for_timeout(50)
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "joy"
        )
        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.expression==='neutral'"
        )
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()

    def test_muted_expression_is_visible_and_new_chat_resets_it(self):
        self.page.locator("#soundToggle").click()
        self.submit("음소거 중 표정 시험")
        self.finish("[joy] 반가워!", audio=wav_fixture())
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "joy"
        )
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-mouth-open"), "0.00"
        )
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").inner_text(),
            "반가워!",
        )
        self.page.locator("#newChat").click()
        self.wait_ready()
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "neutral"
        )

    def test_interrupted_expression_cannot_return_from_old_audio(self):
        self.submit("중단 표정 시험")
        old = self.fixture.current_request
        self.fixture.turn_message(
            "audio", display_text={"text": "[joy] 첫 답변"}, audio=wav_fixture(2)
        )
        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.expression==='joy'"
        )
        self.page.locator("#stopButton").click()
        self.wait_ready()
        self.fixture.send(
            {
                "type": "audio",
                "request_id": old,
                "display_text": {"text": "[joy] 늦은 답변"},
                "audio": wav_fixture(),
            }
        )
        self.page.wait_for_timeout(100)
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-expression"), "neutral"
        )
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-mouth-open"), "0.00"
        )

    def test_mouth_follows_audio_envelope_and_closes_immediately_on_stop(self):
        self.submit("입 움직임 시험")
        self.fixture.turn_message("text-response", display_text={"text": "음성 시험"})
        self.fixture.turn_message(
            "audio",
            display_text={"text": "음성 시험"},
            audio=wav_fixture(2),
            volumes=[0.85] * 100,
            slice_length=20,
        )
        self.page.wait_for_function(
            "Number(document.querySelector('#mascot').dataset.mouthOpen)>0.5",
            timeout=5000,
        )
        self.page.locator("#stopButton").click()
        self.wait_ready()
        self.assertEqual(
            self.page.locator("#mascot").get_attribute("data-mouth-open"), "0.00"
        )

    def test_greeting_moves_arm_and_returns_without_sending_chat(self):
        self.page.locator("#greetButton").click()
        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.greeting==='true'"
        )
        arm = self.page.locator('#mascot g[data-layer="ArmR_Base"]').first
        self.assertNotEqual(arm.get_attribute("transform"), "rotate(0 337 533)")
        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.greeting==='false'"
        )
        self.assertEqual(arm.get_attribute("transform"), "rotate(0 337 533)")
        self.assertFalse(any(m["type"] == "text-input" for m in self.fixture.received))

    def test_reduced_motion_stops_greeting_and_secondary_animation(self):
        self.page.locator("#greetButton").click()
        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.greeting==='true'"
        )
        self.page.locator("#motionToggle").click()
        self.page.wait_for_function(
            "document.querySelector('#mascot').dataset.greeting==='false'"
        )
        self.assertEqual(
            self.page.locator('#mascot g[data-layer="ArmR_Base"]').first.get_attribute(
                "transform"
            ),
            "rotate(0 337 533)",
        )
        self.assertEqual(
            self.page.locator("#mascot").evaluate(
                "el=>getComputedStyle(el).animationName"
            ),
            "none",
        )

    def test_mobile_composer_stays_visible_with_long_conversation(self):
        self.page.set_viewport_size({"width": 360, "height": 640})
        for index in range(3):
            self.submit(f"대화 {index}")
            self.finish("조금 긴 답변도 대화창 안에서 읽을 수 있어. " * 12)
        self.page.evaluate("window.scrollTo(0,0)")
        layout = self.page.locator("#composer").bounding_box()
        self.assertLess(layout["y"] + layout["height"], 640)
        self.assertFalse(
            self.page.evaluate("document.documentElement.scrollWidth>innerWidth")
        )

    def test_unsafe_svg_keeps_the_image_fallback_and_does_not_execute(self):
        self.page.route(
            "**/layers/sogangi-visible-layers.svg",
            lambda route: route.fulfill(
                status=200,
                content_type="image/svg+xml",
                body='<svg xmlns="http://www.w3.org/2000/svg" onload="window.__svgInjected=true"><script>window.__svgInjected=true</script></svg>',
            ),
        )
        self.page.reload(wait_until="networkidle")
        self.wait_ready()
        self.assertFalse(self.page.evaluate("Boolean(window.__svgInjected)"))
        self.assertIsNone(self.page.locator("#mascot").get_attribute("data-renderer"))
        self.assertEqual(self.page.locator("#mascot image").count(), 1)

    def test_disconnect_releases_microphone_without_uploading_a_recording(self):
        self.page.context.grant_permissions(["microphone"])
        self.page.evaluate("""() => {
          const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
          navigator.mediaDevices.getUserMedia = async (...args) => {const stream=await original(...args);window.__testTracks=stream.getTracks();return stream;};
        }""")
        uploads = []
        self.page.on(
            "request",
            lambda request: uploads.append(request.url)
            if request.url.endswith("/asr")
            else None,
        )
        self.page.locator("#micButton").click()
        self.page.wait_for_function(
            "document.querySelector('#micButton').getAttribute('aria-pressed')==='true'",
            timeout=10000,
        )
        self.fixture.route.close(code=1001, reason="fixture microphone disconnect")
        self.page.wait_for_function(
            "window.__testTracks.every(track=>track.readyState==='ended')"
        )
        self.page.wait_for_timeout(100)
        self.assertEqual(uploads, [])
        self.assertEqual(
            self.page.locator("#micButton").get_attribute("aria-pressed"), "false"
        )

    def test_delayed_play_rejection_cannot_overwrite_a_user_stop_notice(self):
        self.page.evaluate(
            "() => {HTMLMediaElement.prototype.play=function(){return new Promise((resolve,reject)=>{window.__rejectPlay=reject;});};}"
        )
        self.submit("빠른 중단 시험")
        self.fixture.turn_message(
            "audio",
            display_text={"text": "시험 답변"},
            audio=wav_fixture(2),
            volumes=[0.7] * 100,
            slice_length=20,
        )
        self.page.wait_for_function("typeof window.__rejectPlay==='function'")
        self.page.locator("#stopButton").click()
        self.wait_ready()
        notice = self.page.locator("#noticeText").inner_text()
        self.page.evaluate(
            "window.__rejectPlay(new DOMException('interrupted','AbortError'))"
        )
        self.page.wait_for_timeout(50)
        self.assertEqual(self.page.locator("#noticeText").inner_text(), notice)

    def test_draft_can_be_written_while_waiting_and_is_not_lost(self):
        self.submit("첫 번째 요청")
        self.page.locator("#messageInput").fill("다음에 보낼 초안")
        self.finish("첫 번째 응답")
        self.assertEqual(
            self.page.locator("#messageInput").input_value(), "다음에 보낼 초안"
        )

    def test_text_arrives_before_audio_without_duplicate_bubbles(self):
        self.submit("인사해 줘")
        self.fixture.turn_message("text-response", display_text={"text": "반가워!"})
        self.page.wait_for_function(
            "document.querySelector('.message.assistant')?.textContent.includes('반가워!')"
        )
        self.assertTrue(self.page.locator("#sendButton").is_disabled())
        self.fixture.turn_message(
            "audio", display_text={"text": "반가워!"}, audio=wav_fixture()
        )
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").all_text_contents(),
            ["반가워!"],
        )

    def test_muted_reply_acknowledges_once_even_with_duplicate_completion(self):
        self.page.locator("#soundToggle").click()
        self.submit("음소거 시험")
        self.finish(audio=wav_fixture())
        self.fixture.turn_message("backend-synth-complete")
        self.page.wait_for_timeout(50)
        self.assertEqual(
            sum(
                m["type"] == "frontend-playback-complete" for m in self.fixture.received
            ),
            1,
        )

    def test_stop_and_new_turn_ignore_old_request_messages(self):
        self.submit("첫 요청")
        old = self.fixture.current_request
        self.page.locator("#stopButton").click()
        self.wait_ready()
        self.submit("새 요청")
        self.assertNotEqual(old, self.fixture.current_request)
        self.fixture.send(
            {
                "type": "text-response",
                "request_id": old,
                "display_text": {"text": "오래된 응답"},
            }
        )
        self.fixture.send(
            {"type": "control", "request_id": old, "text": "conversation-chain-end"}
        )
        self.finish("새 요청의 답변")
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").all_text_contents(),
            ["새 요청의 답변"],
        )

    def test_response_is_text_and_cannot_inject_html(self):
        self.submit("안전한 표시 시험")
        text = '<img src="missing" onerror="window.__injected=true">'
        self.finish(text)
        self.assertEqual(self.page.locator(".message.assistant img").count(), 0)
        self.assertFalse(self.page.evaluate("Boolean(window.__injected)"))
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").inner_text(), text
        )

    def test_disconnect_cleans_up_and_reconnect_starts_a_working_conversation(self):
        self.submit("연결 끊김 시험")
        self.fixture.route.close(code=1001, reason="fixture disconnect")
        self.page.wait_for_function(
            "document.querySelector('#connection').textContent==='연결 끊김'"
        )
        self.assertTrue(self.page.locator("#sendButton").is_disabled())
        self.page.locator("#retry").click()
        self.wait_ready()
        self.submit("다시 연결했어")
        self.finish("다시 반가워!")
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").all_text_contents(),
            ["다시 반가워!"],
        )

    def test_incomplete_expression_only_reply_shows_a_recoverable_notice(self):
        self.submit("불완전 응답 시험")
        self.finish("[neutral")
        self.assertEqual(self.page.locator(".message.assistant").count(), 0)
        self.assertTrue(self.page.locator("#notice").is_visible())
        self.assertFalse(self.page.locator("#sendButton").is_disabled())

    def test_server_failure_finishes_without_claiming_the_user_interrupted(self):
        self.submit("서버 오류 시험")
        self.fixture.turn_message("error", message="fixture timeout")
        self.fixture.turn_message(
            "audio", audio=wav_fixture(), display_text={"text": ""}
        )
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.assertTrue(self.page.locator("#notice").is_visible())
        self.assertFalse(
            any(m["type"] == "interrupt-signal" for m in self.fixture.received)
        )
        self.submit("다시 물어볼게")
        self.finish("이번에는 정상 응답이야!")
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").inner_text(),
            "이번에는 정상 응답이야!",
        )

    def test_saved_history_restores_messages_and_preserves_original_user_input(self):
        self.page.locator("#historyButton").click()
        self.page.locator(".history-item").click()
        self.wait_ready()
        self.assertFalse(self.page.locator("#historyDialog").is_visible())
        self.assertEqual(
            self.page.locator(".message.user .message-body").inner_text(),
            "[neutral]도 원래 입력 그대로",
        )
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").inner_text(),
            "기억을 불러왔어!",
        )
        self.assertEqual(self.page.locator(".message").count(), 2)


if __name__ == "__main__":
    output = Path("tmp/sogangi-browser")
    output.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
