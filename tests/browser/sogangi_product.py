"""Daily-use recovery/settings checks. No model or TTS API calls."""

from pathlib import Path
import hashlib
import io
import json
import struct
import unittest
import zipfile

from sogangi_smoke import SogangiBrowserCase


class SogangiProductTests(SogangiBrowserCase):
    def test_art_handoff_download_contains_valid_layers_and_psd(self):
        self.page.goto(
            self.page.url.split("/web-tool/")[0] + "/web-tool/sogangi/live2d-plan.html",
            wait_until="networkidle",
        )
        self.assertEqual(self.page.locator("#layerButtons button").count(), 10)
        with self.page.expect_download() as download_info:
            self.page.locator("#downloadArt").click()
        with zipfile.ZipFile(
            io.BytesIO(Path(download_info.value.path()).read_bytes())
        ) as bundle:
            self.assertEqual(
                len(
                    [
                        name
                        for name in bundle.namelist()
                        if name.startswith("layers/") and name.endswith(".png")
                    ]
                ),
                24,
            )
            manifest = json.loads(bundle.read("handoff-manifest.json"))
            data = bundle.read("sogangi-visible-parts.psd")
            signature, version, _, channels, height, width, depth, mode = struct.unpack(
                ">4sH6sHIIHH", data[:26]
            )
            self.assertEqual(
                (signature, version, channels, height, width, depth, mode),
                (b"8BPS", 1, 4, 2048, 2048, 8, 3),
            )
            self.assertEqual(hashlib.sha256(data).hexdigest(), manifest["psd_sha256"])
            self.assertEqual(manifest["layer_count"], 24)
            self.assertFalse(manifest["official_layered_source"])

    def test_large_history_list_renders_in_batches_and_searches_all_items(self):
        self.fixture.history_items = [
            {
                "uid": f"saved-{index}",
                "timestamp": "2026-11-02T12:00:00",
                "latest_message": {"content": f"기록 {index}"},
            }
            for index in range(1000)
        ]
        self.page.locator("#historyButton").click()
        self.page.wait_for_function(
            "document.querySelectorAll('.history-item').length===30"
        )
        self.page.locator(".history-more").click()
        self.assertEqual(self.page.locator(".history-item").count(), 60)
        self.page.locator("#historySearch").fill("기록 99")
        self.assertEqual(self.page.locator(".history-item").count(), 11)

    def test_one_hundred_fixture_turns_then_refresh_preserve_all_messages(self):
        for index in range(100):
            self.submit(f"연속 대화 {index}")
            self.finish(f"연속 응답 {index}")
        self.assertEqual(self.page.locator(".message").count(), 200)
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()
        self.assertEqual(self.page.locator(".message").count(), 200)
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").last.inner_text(),
            "연속 응답 99",
        )
        self.assertEqual(self.fixture.history, 1)

    def test_repeated_reconnects_do_not_create_histories_or_resend_questions(self):
        self.submit("반복 연결 전에 저장할 대화")
        self.finish("연결이 돌아와도 같은 기록이야.")
        for _ in range(10):
            self.fixture.route.close(code=1001, reason="synthetic repeated disconnect")
            self.page.wait_for_function(
                "document.querySelector('#connection').textContent==='연결 끊김'"
            )
            self.page.locator("#retry").click()
            self.wait_ready()
        self.assertEqual(self.fixture.history, 1)
        self.assertEqual(
            sum(m["type"] == "text-input" for m in self.fixture.received), 1
        )
        self.assertEqual(self.page.locator(".message").count(), 2)

    def test_preferences_persist_after_refresh(self):
        self.page.locator("#settingsButton").click()
        self.page.locator("#volumeInput").evaluate(
            "el=>{el.value='35';el.dispatchEvent(new Event('input',{bubbles:true}));}"
        )
        self.page.locator("#rateInput").select_option("1.3")
        self.page.locator("#backgroundInput").select_option("paper")
        self.page.locator("#largeTextInput").check()
        self.page.locator("#reducedMotionInput").check()
        self.page.locator("#mutedInput").check()
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()
        self.assertEqual(
            self.page.locator("body").get_attribute("data-background"), "paper"
        )
        self.assertTrue(
            self.page.locator("body").evaluate(
                "el=>el.classList.contains('large-text') && el.classList.contains('reduce-motion')"
            )
        )
        self.assertEqual(
            self.page.locator("#soundToggle").get_attribute("aria-pressed"), "true"
        )
        self.page.locator("#settingsButton").click()
        self.assertEqual(self.page.locator("#volumeInput").input_value(), "35")
        self.assertEqual(self.page.locator("#rateInput").input_value(), "1.3")
        self.page.keyboard.press("Escape")
        self.assertTrue(
            self.page.locator("#settingsButton").evaluate(
                "el=>el===document.activeElement"
            )
        )

    def test_volume_and_speed_apply_to_real_browser_audio(self):
        self.page.evaluate("""() => {
          const original=HTMLMediaElement.prototype.play;
          window.__mediaSettings=[];
          HTMLMediaElement.prototype.play=function(...args){window.__mediaSettings.push({volume:this.volume,rate:this.playbackRate});return original.apply(this,args);};
        }""")
        self.page.locator("#settingsButton").click()
        self.page.locator("#volumeInput").evaluate(
            "el=>{el.value='35';el.dispatchEvent(new Event('input',{bubbles:true}));}"
        )
        self.page.locator("#rateInput").select_option("1.3")
        self.page.locator("#settingsClose").click()
        self.submit("음량과 속도 확인")
        from sogangi_smoke import wav_fixture

        self.finish("설정된 속도로 말해.", audio=wav_fixture())
        self.assertEqual(
            self.page.evaluate("window.__mediaSettings"),
            [{"volume": 0.35, "rate": 1.3}],
        )

    def test_refresh_restores_history_and_draft_without_resending(self):
        self.submit("내가 좋아하는 색은 보라색이야")
        self.finish("보라색을 좋아하는구나!")
        self.page.locator("#messageInput").fill("다음에 물어볼 초안")
        before = sum(m["type"] == "text-input" for m in self.fixture.received)
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()
        self.assertEqual(
            self.page.locator("#messageInput").input_value(), "다음에 물어볼 초안"
        )
        self.assertEqual(
            self.page.locator(".message.assistant .message-body").inner_text(),
            "보라색을 좋아하는구나!",
        )
        self.assertEqual(self.fixture.history, 1)
        self.assertEqual(
            sum(m["type"] == "text-input" for m in self.fixture.received), before
        )

    def test_automatic_reconnect_restores_without_duplicate_request(self):
        self.submit("연결이 끊기기 전 질문")
        self.page.locator("#messageInput").fill("연결 중에도 남겨둘 초안")
        self.fixture.route.close(code=1001, reason="synthetic transient disconnect")
        self.page.wait_for_function(
            "document.querySelector('#connection').textContent==='연결 끊김'"
        )
        self.wait_ready()
        self.assertEqual(self.fixture.history, 1)
        self.assertEqual(
            sum(m["type"] == "text-input" for m in self.fixture.received), 1
        )
        self.assertEqual(
            self.page.locator("#messageInput").input_value(), "연결 중에도 남겨둘 초안"
        )

    def test_missing_saved_history_falls_back_without_overwriting_it(self):
        self.page.locator("#messageInput").fill("보존할 초안")
        self.fixture.histories.clear()
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()
        self.assertEqual(self.fixture.history, 2)
        self.assertIn(
            "이전 기록을 불러오지 못해", self.page.locator("#noticeText").inner_text()
        )
        self.assertEqual(
            self.page.locator("#messageInput").input_value(), "보존할 초안"
        )

    def test_failed_question_can_be_restored_without_automatic_resend(self):
        self.submit("다시 적을 원래 질문")
        self.fixture.turn_message("error", message="synthetic failure")
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.page.locator("#restoreQuestion").click()
        self.assertEqual(
            self.page.locator("#messageInput").input_value(), "다시 적을 원래 질문"
        )
        self.assertEqual(
            sum(m["type"] == "text-input" for m in self.fixture.received), 1
        )

    def test_question_recovery_cannot_overwrite_an_existing_draft(self):
        self.submit("다시 적을 질문")
        self.page.locator("#messageInput").fill("사용자가 쓰고 있는 다른 초안")
        self.fixture.turn_message("error", message="synthetic failure")
        self.fixture.turn_message("backend-synth-complete")
        self.wait_ready()
        self.page.locator("#restoreQuestion").click()
        self.assertEqual(
            self.page.locator("#messageInput").input_value(),
            "사용자가 쓰고 있는 다른 초안",
        )

    def test_history_search_and_utf8_download(self):
        self.submit("내려받을 한글 대화")
        self.finish("대화를 파일로 받을 수 있어.")
        self.page.locator("#historyButton").click()
        self.page.locator(".history-item").wait_for()
        self.page.locator("#historySearch").fill("없는 검색어")
        self.assertEqual(self.page.locator(".history-item").count(), 0)
        self.page.locator("#historySearch").fill("시험")
        self.assertEqual(self.page.locator(".history-item").count(), 1)
        with self.page.expect_download() as download_info:
            self.page.locator("#exportChat").click()
        text = Path(download_info.value.path()).read_text(encoding="utf-8-sig")
        self.assertIn("나: 내려받을 한글 대화", text)
        self.assertIn("서강이: 대화를 파일로 받을 수 있어.", text)

    def test_blocked_browser_storage_does_not_break_chat(self):
        self.page.add_init_script(
            "Storage.prototype.getItem=function(){throw new DOMException('synthetic denied','SecurityError')}; Storage.prototype.setItem=function(){throw new DOMException('synthetic full','QuotaExceededError')};"
        )
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()
        self.submit("저장소 오류가 있어도 대화")
        self.finish("현재 화면에서 대화할 수 있어.")
        self.page.locator("#settingsButton").click()
        self.page.locator("#largeTextInput").check()
        self.assertIn(
            "저장하지 못했어요", self.page.locator("#settingsStatus").inner_text()
        )

    def test_corrupt_preferences_fall_back_to_defaults(self):
        self.page.evaluate("localStorage.setItem('sogangi.preferences.v1','{broken')")
        self.page.reload(wait_until="domcontentloaded")
        self.wait_ready()
        self.assertEqual(
            self.page.locator("body").get_attribute("data-background"), "campus"
        )
        self.page.locator("#settingsButton").click()
        self.assertEqual(self.page.locator("#volumeInput").input_value(), "80")


if __name__ == "__main__":
    unittest.main(verbosity=2)
