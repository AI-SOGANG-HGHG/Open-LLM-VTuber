"""Studio edit and chat regressions against an isolated local server."""

import os
import unittest

from playwright.sync_api import expect, sync_playwright

from ivory_crown import StudioChatFixture


class StudioEditingTests(unittest.TestCase):
    def setUp(self):
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("SOGANGI_BROWSER")
        )
        self.addCleanup(browser.close)
        self.context = browser.new_context()
        self.page = self.context.new_page()
        self.fixture = StudioChatFixture()
        self.page.route_web_socket("**/client-ws", self.fixture.connect)
        base = os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393").rstrip("/")
        self.page.goto(f"{base}/web-tool/platform/")
        self.page.locator("#loginUsername").fill("편집 테스트")
        self.page.locator("#loginSubmit").click()
        card = self.page.locator("#characterGrid article").filter(
            has=self.page.get_by_role("heading", name="강이서", exact=True)
        )
        with self.page.expect_response("**/studio/agents/import") as registration:
            card.get_by_role("link", name="설정", exact=True).click()
        self.fixture.registration = registration.value.json()
        expect(self.page.locator("#settingsForm")).to_be_visible()

    def tab(self, name):
        self.page.get_by_role("navigation", name="캐릭터 관리 메뉴").get_by_role(
            "link", name=name, exact=True
        ).click()

    def test_suggestions_protect_sample_and_live_drafts(self):
        self.tab("샘플 대화")
        draft = "아직 작성 중인 메시지"
        sample = self.page.locator("#chatInput")
        sample_button = self.page.locator('[data-action="suggest"]').first
        sample.fill(draft)
        expect(sample_button).to_be_hidden()
        sample_button.dispatch_event("click")
        expect(sample).to_have_value(draft)
        sample.fill("")
        sample_button.click()
        expect(self.page.locator("#chatMessages .chat-message.user")).to_have_text("안녕!")

        self.tab("음성·Live2D 대화")
        frame = self.page.frame_locator("#studioFrame")
        live = frame.locator("#messageInput")
        prompt = frame.locator("[data-prompt]").filter(has_text="응원이 필요해")
        expect(prompt).to_be_enabled()
        live.fill(draft)
        self.page.reload()
        expect(live).to_have_value(draft)
        expect(prompt).to_be_hidden()
        prompt.dispatch_event("click")
        expect(live).to_have_value(draft)
        self.assertFalse(any(m["type"] == "text-input" for m in self.fixture.received))
        live.fill("")
        prompt.click()
        expect(frame.locator("#messages .message.user")).to_contain_text("짧게 응원해 줘.")
