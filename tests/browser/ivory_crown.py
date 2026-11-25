"""Exercise Kang Iseo's default profile, rendering fallbacks, and Studio audio."""

import json
import os
import re
from pathlib import Path
import unittest

from playwright.sync_api import expect, sync_playwright

from sogangi_smoke import ChatFixture, wav_fixture


KANG_ISEO_BUNDLE = "**/live2d-models/kang-iseo/runtime/**"


def wait_for_blink(canvas):
    # Web assertions may poll less often than the duration of one blink.
    canvas.evaluate("""canvas => new Promise((resolve, reject) => {
        const observer = new MutationObserver(() => {
            if (Number(canvas.dataset.eyeOpen) < 0.9) {
                clearTimeout(timeout);
                observer.disconnect();
                resolve();
            }
        });
        const timeout = setTimeout(() => {
            observer.disconnect();
            reject(Error('No blink rendered'));
        }, 6500);
        observer.observe(canvas, { attributes: true, attributeFilter: ['data-eye-open'] });
    })""")


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

    def expression(self, name):
        self.turn_message(
            "studio-turn-context",
            preset={"label": "강이서"},
            affect={
                "valence": -0.5 if name in ("anger", "sadness") else 0.5,
                "arousal": 0.3 if name == "sadness" else 0.7,
                "dominance": 0.5,
            },
            appraisal="ok",
            retrieval="ok",
            rules=[],
            memories=[],
            expression=name,
        )


class IvoryCrownTests(unittest.TestCase):
    def open_default_character_settings(self, page, base):
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
        return fixture

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
            page.route(KANG_ISEO_BUNDLE, lambda route: route.fulfill(status=404))
            fixture = self.open_default_character_settings(page, base)
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

            wait_for_blink(canvas)
            expect(canvas).to_have_attribute("data-eye-open", "1")
            frame.locator("#motionToggle").click()
            neutral = canvas.evaluate(
                """canvas => [...canvas.getContext('2d').getImageData(480, 554, 74, 36).data]"""
            )
            frame.locator("#messageInput").fill("입이 움직이는지 확인해 줘.")
            frame.locator("#sendButton").click()
            expect(frame.locator("#stopButton")).to_be_enabled()
            fixture.expression("joy")
            fixture.turn_message(
                "text-response", display_text={"text": "[surprise] 확인 중이에요."}
            )
            fixture.turn_message(
                "audio",
                audio=wav_fixture(2),
                volumes=[0.75] * 100,
                slice_length=20,
            )
            expect(canvas).to_have_attribute("data-expression", "joy")
            expect(canvas).to_have_attribute("data-eye-open", "1")
            expect(canvas).to_have_attribute("data-applied-mouth", "0.75")
            fixture.expression("surprise")
            fixture.turn_message(
                "text-response", display_text={"text": "[surprise] 두 번째 문장이에요."}
            )
            expect(frame.locator("#messages .message.assistant")).to_contain_text(
                "두 번째 문장"
            )
            expect(canvas).to_have_attribute("data-expression", "joy")
            moving = canvas.evaluate(
                """canvas => [...canvas.getContext('2d').getImageData(480, 554, 74, 36).data]"""
            )
            self.assertNotEqual(moving, neutral)
            frame.locator("#stopButton").click()
            expect(canvas).to_have_attribute("data-applied-mouth", "0")
            expect(canvas).to_have_attribute("data-expression", "neutral")
            restored = canvas.evaluate(
                """canvas => [...canvas.getContext('2d').getImageData(480, 554, 74, 36).data]"""
            )
            self.assertEqual(restored, neutral)

            frame.locator("#soundToggle").click()
            frame.locator("#messageInput").fill("놀라는 표정을 확인해 줘.")
            frame.locator("#sendButton").click()
            fixture.expression("surprise")
            fixture.turn_message("text-response", display_text={"text": "뜻밖이네요."})
            expect(canvas).to_have_attribute("data-expression", "surprise")
            expect(canvas).to_have_attribute("data-eye-open", "1")
            expect(canvas).to_have_attribute("data-applied-mouth", "0")
            frame.locator("#stopButton").click()

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
            expect(frame.locator("#avatarStatus")).to_contain_text("2D 모드")
            self.assertFalse(errors, errors)
            browser.close()

    def test_kang_iseo_cubism_bindings_and_context_loss(self):
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393").rstrip("/")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("SOGANGI_BROWSER")
            )
            page = browser.new_page()
            page.goto(f"{base}/web-tool/platform/")
            page.evaluate("""async () => {
                const { StudioAvatarRenderer } = await import('./runtime/js/avatars/live2d-avatar.js');
                const stage = document.createElement('div');
                stage.style.cssText = 'position:relative;width:320px;height:480px';
                stage.innerHTML = '<svg id="testHost"></svg><canvas id="testCanvas"></canvas>';
                document.body.replaceChildren(stage);
                const renderer = new StudioAvatarRenderer(stage.firstElementChild,
                    stage.lastElementChild, () => {}, 'ivory-crown');
                window.testAvatar = renderer;
                await renderer.init('live2d');
            }""")
            host = page.locator("#testHost")
            canvas = page.locator("#testCanvas")
            expect(host).to_have_attribute("data-renderer", "live2d")
            expect(canvas).to_have_attribute("data-loaded", "true")
            wait_for_blink(canvas)
            page.evaluate("testAvatar.setReducedMotion(true)")
            expect(canvas).to_have_attribute("data-eye-open", "1")
            neutral = canvas.screenshot()
            page.evaluate("testAvatar.setMouthOpen(0.75)")
            expect(canvas).to_have_attribute("data-applied-mouth", "0.75")
            speaking = canvas.screenshot()
            self.assertNotEqual(speaking, neutral)
            faces = {speaking}
            for expression in ("joy", "surprise", "anger", "sadness"):
                page.evaluate("name => testAvatar.setExpression(name)", expression)
                expect(canvas).to_have_attribute("data-expression", expression)
                pixels = canvas.screenshot()
                self.assertNotIn(pixels, faces, expression)
                faces.add(pixels)
                expect(canvas).to_have_attribute("data-applied-mouth", "0.75")
                if expression in ("anger", "sadness"):
                    page.evaluate("testAvatar.setReducedMotion(false)")
                    wait_for_blink(canvas)
                    expect(canvas).to_have_attribute("data-applied-mouth", "0.75")
                    page.evaluate("testAvatar.setReducedMotion(true)")
            canvas.evaluate(
                "canvas => canvas.dispatchEvent(new Event('webglcontextlost', {cancelable: true}))"
            )
            expect(host).to_have_attribute("data-renderer", "canvas2d")
            expect(canvas).to_have_attribute("data-expression", "sadness")
            expect(canvas).to_have_attribute("data-applied-mouth", "0.75")
            fallback_sadness = canvas.screenshot()
            page.evaluate("testAvatar.setExpression('anger')")
            expect(canvas).to_have_attribute("data-expression", "anger")
            self.assertNotEqual(canvas.screenshot(), fallback_sadness)
            expect(canvas).to_have_attribute("data-applied-mouth", "0.75")
            page.evaluate("testAvatar.setMouthOpen(0)")
            expect(canvas).to_have_attribute("data-applied-mouth", "0")
            page.evaluate("testAvatar.dispose()")
            browser.close()

    def test_inspector_renders_kang_iseo_expressions_and_eyes(self):
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393").rstrip("/")
        model = "/live2d-models/kang-iseo/runtime/kang-iseo.model3.json"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("SOGANGI_BROWSER")
            )
            page = browser.new_page(viewport={"width": 1280, "height": 950})
            page.goto(f"{base}/web-tool/sogangi/live2d-preview.html?model=kang-iseo")
            stage = page.locator("#modelStage")
            expect(stage).to_have_attribute("data-model-url", model)
            canvas = page.locator("#modelCanvas")
            neutral = canvas.screenshot()
            for control, value, parameter in (
                ("eyeL", 0, "ParamEyeLOpen"),
                ("eyeR", 0, "ParamEyeROpen"),
            ):
                page.locator(f"#parameter-{control}").evaluate(
                    "(input, value) => {input.value = value; input.dispatchEvent(new Event('input'));}",
                    value,
                )
                page.wait_for_function(
                    "([id, value]) => JSON.parse(document.querySelector('#modelStage').dataset.appliedParameters)[id] === value",
                    arg=[parameter, value],
                )
                self.assertNotEqual(canvas.screenshot(), neutral, parameter)
                page.locator("#resetPose").click()
                page.wait_for_function(
                    "([id, value]) => JSON.parse(document.querySelector('#modelStage').dataset.appliedParameters)[id] === value",
                    arg=[parameter, 1 if control.startswith("eye") else 0],
                )
                self.assertEqual(canvas.screenshot(), neutral, parameter)
            def face_regions():
                box = canvas.bounding_box()
                scale = min(box["width"] / 1024, box["height"] / 1536) * 0.92
                left = box["x"] + (box["width"] - 1024 * scale) / 2
                top = box["y"] + (box["height"] - 1536 * scale) / 2
                return [
                    page.screenshot(
                        clip={
                            "x": left + x * scale,
                            "y": top + y * scale,
                            "width": width * scale,
                            "height": height * scale,
                        }
                    )
                    for x, y, width, height in (
                        (417, 408, 67, 22), (419, 445, 64, 46),
                        (481, 553, 72, 28)
                    )
                ]

            regions = face_regions()
            seen_regions = [{pixels} for pixels in regions]
            output = Path("tmp/kang-iseo-browser")
            output.mkdir(parents=True, exist_ok=True)
            canvas.screenshot(path=output / "face-neutral.png")
            buttons = page.get_by_role("group", name="표정 선택")
            expect(buttons.get_by_role("button")).to_have_count(8)
            neutral_button = buttons.get_by_role("button", name="대기·중립")
            expect(neutral_button).to_have_attribute("aria-pressed", "true")
            for expression, label in (("joy", "기쁨"), ("surprise", "놀람"), ("anger", "분노"), ("sadness", "슬픔")):
                button = buttons.get_by_role("button", name=label, exact=True)
                button.click()
                expect(stage).to_have_attribute("data-expression", expression)
                expect(button).to_have_attribute("aria-pressed", "true")
                expect(buttons.locator('[aria-pressed="true"]')).to_have_count(1)
                for seen, changed in zip(seen_regions, face_regions()):
                    self.assertNotIn(changed, seen, expression)
                    seen.add(changed)
                canvas.screenshot(path=output / f"face-{expression}.png")
            page.locator("#modelExpression").select_option(label="neutral")
            expect(stage).to_have_attribute("data-expression", "neutral")
            expect(neutral_button).to_have_attribute("aria-pressed", "true")
            self.assertEqual(regions, face_regions())

            variant = page.get_by_label("표정 강도")
            expect(variant).to_have_value("standard")
            variant.select_option("clearer")
            expect(stage).to_have_attribute("data-face-variant", "clearer")
            self.assertEqual(regions, face_regions())
            for expression in ("joy", "surprise", "anger", "sadness"):
                variant.select_option("standard")
                expect(stage).to_have_attribute("data-face-variant", "standard")
                page.locator("#modelExpression").select_option(label=expression)
                expect(stage).to_have_attribute("data-expression", expression)
                standard = canvas.screenshot()
                variant.select_option("clearer")
                expect(stage).to_have_attribute("data-face-variant", "clearer")
                expect(stage).to_have_attribute("data-expression", expression)
                self.assertNotEqual(canvas.screenshot(), standard, expression)
                variant.select_option("standard")
                expect(stage).to_have_attribute("data-face-variant", "standard")
                self.assertEqual(canvas.screenshot(), standard, expression)

            buttons.get_by_role("button", name="생각하기").click()
            expect(stage).to_have_attribute("data-expression", "neutral")
            expect(page.locator("#parameter-eyeL")).to_have_value("0.78")
            buttons.get_by_role("button", name="말하기").click()
            page.wait_for_function("Number(document.querySelector('#modelStage').dataset.appliedMouth) > 0.25")
            expect(page.locator("#parameter-eyeL")).to_have_value("1")
            buttons.get_by_role("button", name="인사", exact=True).click()
            expect(stage).to_have_attribute("data-expression", "joy")
            page.wait_for_function("Number(document.querySelector('#modelStage').dataset.appliedMouth) > 0.25")
            neutral_button.click()
            expect(stage).to_have_attribute("data-expression", "neutral")
            expect(stage).to_have_attribute("data-applied-mouth", "0")
            expect(page.locator("#motionControls")).to_be_hidden()
            expect(page.locator("#parameter-tilt")).to_have_count(0)
            expect(page.locator("#parameter-breath")).to_have_count(0)
            page.goto(f"{base}/web-tool/sogangi/live2d-preview.html?model=kang-iseo-arm")
            expect(stage).to_have_attribute("data-model-url", model)
            expect(page.locator("#motionControls")).to_be_hidden()
            browser.close()

    def test_studio_plays_kang_iseo_cubism_model_and_closes_mouth_on_stop(self):
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393").rstrip("/")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("SOGANGI_BROWSER"),
                args=["--autoplay-policy=no-user-gesture-required"],
            )
            page = browser.new_page(viewport={"width": 1420, "height": 850})
            fixture = self.open_default_character_settings(page, base)
            page.get_by_role("link", name="음성·2D 대화", exact=True).click()
            expect(page.locator("#runtimeStatus")).to_contain_text("대화할 수 있어요")
            frame = page.frame_locator("#studioFrame")
            canvas = frame.locator("#avatarCanvas")
            expect(frame.locator("#mascot")).to_have_attribute(
                "data-renderer", "live2d"
            )
            expect(canvas).to_have_attribute("data-loaded", "true")
            output = Path("tmp/kang-iseo-browser")
            output.mkdir(parents=True, exist_ok=True)
            frame.locator("#motionToggle").click()
            neutral = canvas.screenshot(path=output / "studio-neutral.png")
            frame.locator("#motionToggle").click()

            for expression, prompt, response in (
                ("joy", "오늘 발표를 잘 마쳤어.", "발표를 잘 마쳤다니 기뻐요."),
                ("surprise", "친구들이 깜짝 생일 파티를 열어 줬어.", "정말 깜짝 놀랐겠어요."),
                ("anger", "또 부당한 판정이 나왔어.", "그 판정은 부당하네요."),
                (
                    "sadness",
                    "오래 키우던 강아지를 떠나보냈어.",
                    "마음이 많이 무겁겠어요.",
                ),
            ):
                frame.locator("#messageInput").fill(prompt)
                frame.locator("#sendButton").click()
                expect(frame.locator("#stopButton")).to_be_enabled()
                expect(canvas).to_have_attribute("data-eye-open", re.compile(r"^0\.(?:78|779)"))
                fixture.expression(expression)
                fixture.turn_message("text-response", display_text={"text": response})
                fixture.turn_message(
                    "audio", audio=wav_fixture(3), volumes=[0.75] * 150, slice_length=20
                )
                expect(canvas).to_have_attribute("data-expression", expression)
                expect(canvas).to_have_attribute("data-applied-mouth", "0.75")
                self.assertNotEqual(
                    canvas.screenshot(path=output / f"studio-{expression}.png"), neutral
                )
                frame.locator("#stopButton").click()
                expect(canvas).to_have_attribute("data-expression", "neutral")
                expect(canvas).to_have_attribute("data-applied-mouth", "0")
                frame.locator("#motionToggle").click()
                self.assertEqual(canvas.screenshot(), neutral)
                frame.locator("#motionToggle").click()
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
