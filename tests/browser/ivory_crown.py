"""Exercise Kang Iseo's default profile, rendering fallbacks, and Studio audio."""

import json
import os
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
            self.assertEqual(profile["preset_id"], "kang-iseo")
            self.assertIn(
                "차분한 한국어 존댓말", fixture.registration["personality"]["style"]
            )
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
            page.get_by_role("link", name="음성·Live2D 대화", exact=True).click()
            expect(page.locator("#runtimeStatus")).to_contain_text("대화할 수 있어요")
            expect(page.locator("#studioFrame")).to_have_attribute(
                "title", "강이서 음성·Live2D 대화실"
            )
            frame = page.frame_locator("#studioFrame")
            canvas = frame.locator("#avatarCanvas")
            expect(canvas).to_be_visible()
            expect(frame.locator("#welcome p")).to_contain_text(profile["greeting"])
            expect(frame.locator("#mascot")).to_have_attribute(
                "data-renderer", "canvas2d"
            )
            expect(frame.locator("#greetButton")).to_be_hidden()
            self.assertEqual(
                fixture.received[0]["agent_id"], fixture.registration["agent_id"]
            )

            # Wait for a real blink and check the single-layer portrait's motion.
            wait_for_blink(canvas)
            expect(canvas).to_have_attribute("data-eye-open", "1")
            self.assertEqual(
                canvas.evaluate("""canvas => {
                    const [breath] = canvas.getAnimations();
                    breath.pause();
                    breath.currentTime = 2500;
                    return getComputedStyle(canvas).scale;
                }"""),
                "1.008 1.012",
            )
            frame.locator(
                ".stage"
            ).evaluate("""stage => stage.dispatchEvent(new PointerEvent('pointermove', {
                pointerType: 'mouse', clientX: stage.getBoundingClientRect().right,
            }))""")
            self.assertEqual(canvas.evaluate("canvas => canvas.style.rotate"), "2.5deg")

            # Compare the canvas mouth pixels against neutral with blinking paused.
            frame.locator("#motionToggle").click()
            self.assertEqual(
                canvas.evaluate("canvas => canvas.getAnimations().length"), 0
            )
            self.assertEqual(canvas.evaluate("canvas => canvas.style.rotate"), "0deg")
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
            expect(canvas).to_have_attribute("data-eye-open", "0.72")
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
            expect(canvas).to_have_attribute("data-eye-open", "1.1")
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

    def test_inspector_renders_kang_iseo_eye_and_motion_keyforms(self):
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393").rstrip("/")
        model = "/live2d-models/kang-iseo/runtime/kang-iseo.model3.json"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("SOGANGI_BROWSER")
            )
            page = browser.new_page(viewport={"width": 1280, "height": 950})
            page.goto(f"{base}/web-tool/sogangi/live2d-preview.html")
            page.locator("#modelUrl").fill(model)
            page.locator("#loadModel").click()
            stage = page.locator("#modelStage")
            expect(stage).to_have_attribute("data-model-url", model)
            canvas = page.locator("#modelCanvas")
            neutral = canvas.screenshot()
            for control, value, parameter in (
                ("eyeL", 0, "ParamEyeLOpen"),
                ("eyeR", 0, "ParamEyeROpen"),
                ("tilt", 3, "ParamAngleZ"),
                ("breath", 1, "ParamBreath"),
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
            browser.close()

    def test_live2d_filter_and_kang_iseo_preview(self):
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
            page.locator("#loginUsername").fill("테스트 사용자")
            page.locator("#loginSubmit").click()
            page.get_by_role("button", name="Live2D", exact=True).click()
            card = page.locator("#characterGrid .character-card").filter(
                has=page.get_by_role("heading", name="강이서", exact=True)
            )
            expect(card.locator(".card-type")).to_have_text("Live2D 아바타")

            preview = card.get_by_role("button", name="강이서 외형 미리보기")
            dialog = page.locator("#avatarDialog")
            canvas = dialog.locator("#liveAvatarCanvas")
            fallback = dialog.locator("#avatarFallback img")
            preview.click()
            expect(canvas).to_have_attribute("data-loaded", "true", timeout=15000)
            expect(canvas).to_have_attribute("data-expression", "neutral")
            expect(canvas).to_be_visible()
            expect(fallback).to_be_hidden()
            dialog.get_by_role("button", name="닫기").click()
            expect(dialog).to_be_hidden()

            page.route(KANG_ISEO_BUNDLE, lambda route: route.fulfill(status=404))
            preview.click()
            expect(dialog.get_by_role("status")).to_contain_text("이미지로 보여드려요")
            expect(fallback).to_be_visible()
            expect(canvas).to_be_hidden()
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
            page.get_by_role("link", name="음성·Live2D 대화", exact=True).click()
            expect(page.locator("#runtimeStatus")).to_contain_text("대화할 수 있어요")
            frame = page.frame_locator("#studioFrame")
            canvas = frame.locator("#avatarCanvas")
            expect(frame.locator("#mascot")).to_have_attribute(
                "data-renderer", "live2d"
            )
            expect(canvas).to_have_attribute("data-loaded", "true")
            frame.locator("#motionToggle").click()
            output = Path("tmp/kang-iseo-browser")
            output.mkdir(parents=True, exist_ok=True)
            neutral = canvas.screenshot(path=output / "studio-neutral.png")

            for expression, prompt, response in (
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
                self.assertEqual(canvas.screenshot(), neutral)
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
            card = page.locator("#characterGrid .character-card").filter(has=heading)
            with page.expect_response(
                lambda response: response.url == f"{base}/studio/agents/import"
                and response.request.method == "POST"
            ) as registration:
                card.get_by_role("link", name="설정", exact=True).click()
            self.assertTrue(registration.value.ok, registration.value.status)
            seeded = registration.value.json()
            expect(page.locator("#settingsForm")).to_be_visible()
            page.locator('[data-nav="characters"]').click()
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
            expect(form.locator('[name="studioPreset"]')).to_have_value("kang-iseo")
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
            created = creation.value.json()
            profile = created["profile"]
            self.assertEqual(profile["name"], "강이서")
            self.assertEqual(profile["avatar"], "ivory-crown")
            for field in ("preset_id", "description", "greeting", "exploration"):
                self.assertEqual(profile[field], seeded["profile"][field], field)
            self.assertEqual(created["personality"], seeded["personality"])
            self.assertNotEqual(profile["character_id"], "kang-iseo")
            browser.close()

    def test_upgrade_preserves_edited_profiles_and_updates_untouched_default(self):
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393").rstrip("/")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get("SOGANGI_BROWSER")
            )
            for variant in ("untouched", "edited", "registered", "deleted"):
                with self.subTest(variant=variant):
                    page = browser.new_page()
                    page.route(
                        "**/auth/session",
                        lambda route: route.fulfill(json={"enabled": False}),
                    )
                    page.goto(f"{base}/web-tool/platform/")
                    previous = page.evaluate(
                        """async (variant) => {
                        const { createCharacter } = await import('./js/presets.js');
                        const char = createCharacter('kang-iseo', '강이서', '복잡한 고민을 들어주고 다음에 할 일을 차근차근 정리해 줘요.', 'calm', 'ivory-crown');
                        char.favorite = true;
                        char.messages.push({ role: 'user', content: '샘플 대화 기록' });
                        char.memories.push({ id: 'example', text: '기억 노트', at: char.createdAt });
                        if (variant === 'edited') char.greeting = '내가 남긴 인사';
                        if (variant === 'registered') char.agentId = crypto.randomUUID();
                        localStorage.setItem('persona-studio.demo.v1', JSON.stringify({
                            version: 1, catalogVersion: 4, workspaceId: crypto.randomUUID(),
                            characters: variant === 'deleted' ? [] : [char], activities: [],
                        }));
                        return char;
                    }""",
                        variant,
                    )
                    page.reload()
                    page.locator("#loginUsername").fill("테스트 사용자")
                    page.locator("#loginSubmit").click()
                    expect(page.locator("#workspaceView")).to_be_visible()
                    stored = page.evaluate(
                        "JSON.parse(localStorage.getItem('persona-studio.demo.v1'))"
                    )
                    self.assertEqual(stored["catalogVersion"], 5)
                    if variant == "deleted":
                        self.assertEqual(stored["characters"], [])
                    else:
                        (char,) = stored["characters"]
                        for field in ("favorite", "messages", "memories", "createdAt"):
                            self.assertEqual(char[field], previous[field], field)
                        if variant == "untouched":
                            self.assertEqual(char["studioPreset"], "kang-iseo")
                            self.assertNotEqual(char["greeting"], previous["greeting"])
                        else:
                            self.assertFalse(char.get("studioPreset"))
                            self.assertEqual(char["greeting"], previous["greeting"])
                            self.assertEqual(
                                char.get("agentId"), previous.get("agentId")
                            )
                    page.close()
            browser.close()


if __name__ == "__main__":
    unittest.main()
