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

    def test_profile_draft_survives_navigation_and_reload_until_saved_or_discarded(self):
        page = self.page
        greeting = page.locator("#editGreeting")
        original = greeting.input_value()
        greeting.fill("")
        page.locator("#editDescription").fill("수정 중인 소개")
        self.tab("기억 노트")
        page.get_by_role("textbox", name="새 기억").fill("편집 중 등록한 노트")
        page.get_by_role("button", name="기억 추가").click()
        expect(page.locator(".memory-item")).to_contain_text("편집 중 등록한 노트")
        self.tab("프로필·성격")
        expect(greeting).to_have_value("")
        page.reload()
        expect(page.locator("#editDescription")).to_have_value("수정 중인 소개")
        expect(greeting).to_have_value("")
        page.get_by_role("button", name="수정 취소").click()
        expect(greeting).to_have_value(original)
        expect(page.get_by_role("button", name="수정 취소")).to_be_hidden()
        greeting.fill("저장할 첫 인사")
        page.get_by_role("button", name="변경사항 저장").click()
        expect(page.locator("#toast")).to_contain_text("저장했어요")
        page.reload()
        expect(greeting).to_have_value("저장할 첫 인사")
        expect(page.locator("#profileDraftStatus")).to_be_hidden()
        self.tab("기억 노트")
        expect(page.locator(".memory-item")).to_contain_text("편집 중 등록한 노트")

    def test_conflict_keeps_my_changes_and_other_tabs_untouched_fields(self):
        first = self.page
        other = self.context.new_page()
        other.goto(first.url)
        other.locator("#loginUsername").fill("편집 테스트")
        other.locator("#loginSubmit").click()
        expect(other.locator("#settingsForm")).to_be_visible()
        other.locator("#editGreeting").fill("내가 작성 중인 첫 인사")
        first.locator("#editDescription").fill("다른 탭에서 저장한 소개")
        first.locator("#editGreeting").fill("다른 탭에서 저장한 첫 인사")
        first.get_by_role("button", name="변경사항 저장").click()
        expect(first.locator("#toast")).to_contain_text("저장했어요")
        with other.expect_response(lambda r: r.request.method == "PUT") as conflict:
            other.get_by_role("button", name="변경사항 저장").click()
        self.assertEqual(conflict.value.status, 409)
        expect(other.locator("#profileDraftStatus")).to_contain_text("최신 설정")
        expect(other.locator("#editGreeting")).to_have_value("내가 작성 중인 첫 인사")
        expect(other.locator("#editDescription")).to_have_value("다른 탭에서 저장한 소개")
        other.get_by_role("button", name="변경사항 저장").click()
        expect(other.locator("#toast")).to_contain_text("저장했어요")
        first.reload()
        expect(first.locator("#editGreeting")).to_have_value("내가 작성 중인 첫 인사")
        expect(first.locator("#editDescription")).to_have_value("다른 탭에서 저장한 소개")

    def test_previews_follow_the_unsaved_profile_and_restore_it_after_navigation(self):
        page = self.page
        form = page.locator("#settingsForm")
        side = page.locator(".settings-preview")
        large = page.locator("#avatarDialog")
        open_preview = page.get_by_role("button", name="외형 미리보기", exact=True)
        page.locator("#editName").fill("초안 <이서>")
        page.locator("#editDescription").fill("아직 저장하지 않은 소개")
        page.locator("#editGreeting").fill("반가워요!")
        form.locator('label:has([name="avatar"][value="symbol"])').click()
        expect(side.locator(".stage-symbol")).to_be_visible()
        expect(side).to_contain_text("아직 저장하지 않은 소개")
        expect(side.locator("#previewGreeting")).to_have_text("“반가워요!”")
        open_preview.click()
        expect(large.get_by_role("heading")).to_have_text("초안 <이서> · 캐릭터 미리보기")
        expect(large.locator(".stage-symbol")).to_be_visible()
        expect(large.locator("canvas")).to_be_hidden()
        large.get_by_role("button", name="닫기").click()

        form.locator('label:has([name="avatar"][value="mao"])').click()
        expect(side.locator(".asset-credit")).to_contain_text("Live2D Inc.")
        self.tab("기억 노트")
        self.tab("프로필·성격")
        expect(side.locator("#previewName")).to_have_text("초안 <이서>")
        expect(side.locator(".preview-art.mao img")).to_have_attribute("alt", "초안 <이서> 캐릭터")
        open_preview.click()
        expect(large.locator("canvas")).to_have_attribute("data-loaded", "true", timeout=15000)
        expect(large.locator("#avatarCredit")).to_contain_text("Live2D Inc.")
        large.get_by_role("button", name="닫기").click()
        page.get_by_role("button", name="수정 취소").click()
        expect(side.locator(".preview-art.ivory-crown img")).to_be_visible()
        expect(side.locator(".asset-credit")).to_have_count(0)
        open_preview.click()
        expect(large.get_by_role("heading")).to_have_text("강이서 · 캐릭터 미리보기")
        expect(large.locator("canvas")).to_have_attribute("data-loaded", "true", timeout=15000)
