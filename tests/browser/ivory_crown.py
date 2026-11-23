"""Exercise Kang Iseo's default profile, Canvas avatar, and Studio audio queue."""

import json
import os
import unittest

from playwright.sync_api import expect, sync_playwright

from sogangi_smoke import ChatFixture, wav_fixture


class StudioChatFixture(ChatFixture):
    registration = None

    def receive(self, raw):
        message = json.loads(raw)
        if message["type"] != "apply-studio-persona":
            super().receive(raw)
            return
        self.received.append(message)
        profile = self.registration["profile"]
        if (
            message["agent_id"] != self.registration["agent_id"]
            or message["workspace_id"] != profile["workspace_id"]
        ):
            self.send({"type": "studio-persona-error", "code": "character_mismatch"})
            return
        self.send(
            {
                "type": "studio-persona-applied",
                "agent_id": self.registration["agent_id"],
                **{key: profile[key] for key in ("character_id", "avatar", "name")},
            }
        )


class IvoryCrownTests(unittest.TestCase):
    def test_default_character_chat_and_recover_after_canvas_load_failure(self):
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
            card = page.locator("#characterGrid .character-card").filter(
                has=page.get_by_role("heading", name="강이서", exact=True)
            )
            with page.expect_response(
                lambda response: response.url == f"{base}/studio/agents/import"
                and response.request.method == "POST"
            ) as creation:
                card.get_by_role("link", name="설정", exact=True).click()
            self.assertTrue(creation.value.ok, creation.value.status)
            fixture.registration = creation.value.json()
            profile = fixture.registration["profile"]
            self.assertEqual(profile["character_id"], "kang-iseo")
            self.assertEqual(profile["name"], "강이서")
            self.assertEqual(profile["avatar"], "ivory-crown")
            self.assertEqual(profile["tone"], "차분한 존댓말")
            expect(page.locator('#settingsForm [value="ivory-crown"]')).to_be_checked()
            expect(
                page.locator(
                    '#settingsForm .avatar-option:has([value="ivory-crown"]) strong'
                )
            ).to_have_text("강이서")
            expect(page.locator("#settingsAvatar img")).to_have_js_property(
                "complete", True
            )
            self.assertGreater(
                page.locator("#settingsAvatar img").evaluate(
                    "image => image.naturalWidth"
                ),
                0,
            )
            page.get_by_role("link", name="음성·2D 대화", exact=True).click()
            expect(page.locator("#runtimeStatus")).to_contain_text("대화할 수 있어요")
            expect(page.locator("#studioFrame")).to_have_attribute(
                "title", "강이서 음성·2D 대화실"
            )
            frame = page.frame_locator("#studioFrame")
            canvas = frame.locator("#avatarCanvas")
            expect(canvas).to_be_visible()
            expect(frame.locator("#welcome p")).to_contain_text("강이서입니다.")
            expect(frame.locator("#mascot")).to_have_attribute(
                "data-renderer", "canvas2d"
            )
            expect(frame.locator("#greetButton")).to_be_hidden()
            self.assertEqual(
                fixture.received[0]["agent_id"], fixture.registration["agent_id"]
            )

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

    def test_existing_workspace_adds_default_once_and_can_start_from_discover(self):
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393").rstrip("/")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("SOGANGI_BROWSER")
            )
            page = browser.new_page()
            page.route(
                "**/auth/session", lambda route: route.fulfill(json={"enabled": False})
            )
            page.goto(f"{base}/web-tool/platform/")
            page.evaluate("""async () => {
                const { createCharacter } = await import('./js/presets.js');
                const existing = createCharacter('existing', '기존 캐릭터', '내가 작성한 소개', 'warm', 'ivory-crown');
                localStorage.setItem('persona-studio.demo.v1', JSON.stringify({
                    version: 1, catalogVersion: 3, workspaceId: crypto.randomUUID(),
                    characters: [existing], activities: [],
                }));
            }""")
            page.reload()
            page.locator("#loginUsername").fill("테스트 사용자")
            page.locator("#loginSubmit").click()
            heading = page.get_by_role("heading", name="강이서", exact=True)
            expect(heading).to_have_count(1)
            expect(page.locator("#characterGrid .character-card")).to_have_count(2)
            expect(page.get_by_text("내가 작성한 소개", exact=True)).to_be_visible()
            page.reload()
            expect(heading).to_have_count(1)
            page.get_by_role("button", name="강이서 삭제", exact=True).click()
            page.get_by_role("button", name="삭제하기", exact=True).click()
            expect(heading).to_have_count(0)
            page.reload()
            expect(page.get_by_text("내가 작성한 소개", exact=True)).to_be_visible()
            expect(heading).to_have_count(0)

            page.locator('[data-nav="discover"]').click()
            card = page.locator(".character-card").filter(has=heading)
            card.get_by_role("button", name="이 캐릭터로 시작").click()
            form = page.locator("#characterForm")
            expect(form.locator('[name="name"]')).to_have_value("강이서")
            expect(form.locator('[name="studioPreset"]')).to_have_value("calm")
            expect(form.locator('[value="ivory-crown"]')).to_be_checked()
            expect(
                form.locator('.avatar-option:has([value="ivory-crown"]) strong')
            ).to_have_text("강이서")
            with page.expect_response(
                lambda response: response.url == f"{base}/studio/agents"
                and response.request.method == "POST"
            ) as creation:
                form.locator('button[type="submit"]').click()
            self.assertTrue(creation.value.ok, creation.value.status)
            profile = creation.value.json()["profile"]
            self.assertEqual(profile["name"], "강이서")
            self.assertEqual(profile["avatar"], "ivory-crown")
            self.assertEqual(profile["preset_id"], "calm")
            self.assertNotEqual(profile["character_id"], "kang-iseo")
            browser.close()


if __name__ == "__main__":
    unittest.main()
