"""Exercise the Ivory Crown appearance through the real Studio UI and audio queue."""

import json
import os
import unittest

from playwright.sync_api import expect, sync_playwright

from sogangi_smoke import ChatFixture, wav_fixture


class StudioChatFixture(ChatFixture):
    def receive(self, raw):
        message = json.loads(raw)
        if message["type"] != "apply-studio-persona":
            super().receive(raw)
            return
        self.received.append(message)
        profile = message["profile"]
        self.send(
            {
                "type": "studio-persona-applied",
                **{key: profile[key] for key in ("character_id", "avatar", "name")},
            }
        )


class IvoryCrownTests(unittest.TestCase):
    def test_create_chat_and_recover_portrait_after_canvas_load_failure(self):
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393").rstrip("/")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("SOGANGI_BROWSER"),
                args=["--autoplay-policy=no-user-gesture-required"],
            )
            page = browser.new_page(viewport={"width": 1420, "height": 850})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.route(
                "**/auth/session", lambda route: route.fulfill(json={"enabled": False})
            )
            fixture = StudioChatFixture()
            page.route_web_socket("**/client-ws", fixture.connect)
            page.goto(f"{base}/web-tool/platform/")
            page.locator("#loginUsername").fill("테스트 사용자")
            page.locator("#loginSubmit").click()
            page.locator('[data-action="create"]').first.click()
            form = page.locator("#characterForm")
            form.locator('[name="name"]').fill("테스트 대화 상대")
            form.locator('[name="description"]').fill("2D 외형 연결을 확인해요.")
            form.locator(".avatar-option").filter(has_text="Ivory Crown").click()
            form.locator('button[type="submit"]').click()
            expect(page.locator('#settingsForm [value="ivory-crown"]')).to_be_checked()
            expect(page.locator("#settingsAvatar img")).to_have_js_property(
                "complete", True
            )
            self.assertGreater(
                page.locator("#settingsAvatar img").evaluate(
                    "image => image.naturalWidth"
                ),
                0,
            )
            page.get_by_role("navigation", name="캐릭터 관리 메뉴").locator(
                'a[href$="/chat"]'
            ).click()
            expect(page.locator("#runtimeStatus")).to_contain_text("대화할 수 있어요")
            frame = page.frame_locator("#studioFrame")
            canvas = frame.locator("#avatarCanvas")
            expect(canvas).to_be_visible()
            expect(frame.locator("#mascot")).to_have_attribute(
                "data-renderer", "canvas2d"
            )
            expect(frame.locator("#greetButton")).to_be_hidden()
            self.assertEqual(fixture.received[0]["profile"]["avatar"], "ivory-crown")

            # Compare the canvas mouth pixels against neutral with blinking paused.
            frame.locator("#motionToggle").click()
            neutral = canvas.evaluate(
                """canvas => [...canvas.getContext('2d').getImageData(480, 554, 74, 36).data]"""
            )
            frame.locator("#messageInput").fill("입이 움직이는지 확인해 줘.")
            frame.locator("#sendButton").click()
            expect(frame.locator("#stopButton")).to_be_enabled()
            fixture.turn_message(
                "text-response", display_text={"text": "확인 중이에요."}
            )
            fixture.turn_message(
                "audio",
                audio=wav_fixture(2),
                volumes=[0.75] * 100,
                slice_length=20,
            )
            expect(canvas).to_have_attribute("data-applied-mouth", "0.75")
            moving = canvas.evaluate(
                """canvas => [...canvas.getContext('2d').getImageData(480, 554, 74, 36).data]"""
            )
            self.assertNotEqual(moving, neutral)
            frame.locator("#stopButton").click()
            expect(canvas).to_have_attribute("data-applied-mouth", "0")
            restored = canvas.evaluate(
                """canvas => [...canvas.getContext('2d').getImageData(480, 554, 74, 36).data]"""
            )
            self.assertEqual(restored, neutral)

            page.set_viewport_size({"width": 390, "height": 844})
            self.assertTrue(
                page.evaluate("document.documentElement.scrollWidth === innerWidth")
            )
            self.assertTrue(
                canvas.evaluate(
                    "canvas => document.documentElement.scrollWidth === innerWidth"
                )
            )

            # A new document retries initialization and keeps the same portrait
            # even when the animated renderer cannot be downloaded.
            script = "**/shared/ivory-crown-rig.js"
            page.route(script, lambda route: route.abort())
            page.reload()
            expect(page.locator("#runtimeStatus")).to_contain_text("대화할 수 있어요")
            frame.locator("#settingsButton").click()
            expect(frame.locator("#avatarRetry")).to_be_visible()
            expect(frame.locator("#mascot image")).to_have_attribute(
                "href", f"{base}/web-tool/platform/assets/ivory-crown.webp"
            )
            expect(canvas).to_be_hidden()
            page.unroute(script)
            frame.locator("#avatarRetry").click()
            expect(canvas).to_be_visible()
            expect(frame.locator("#avatarRetry")).to_be_hidden()
            self.assertFalse(errors, errors)
            browser.close()


if __name__ == "__main__":
    unittest.main()
