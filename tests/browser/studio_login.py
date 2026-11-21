"""Public page-login, refresh, Live2D, and cross-tab logout; no model requests."""

import json
import re
from pathlib import Path

from dotenv import dotenv_values
from playwright.sync_api import Browser, expect, sync_playwright


def check_session_retry(browser: Browser, url: str) -> None:
    """Verify session checking can be retried without native UUID support."""
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script(
        'Object.defineProperty(Crypto.prototype, "randomUUID", { value: undefined });'
    )
    page.clock.install()
    pending = []
    page.route("**/auth/session", lambda route: pending.append(route), times=1)
    with page.expect_request("**/auth/session"):
        page.goto(url, wait_until="domcontentloaded")
    button = page.locator("#loginSubmit")
    expect(button).to_be_disabled()
    expect(button).to_contain_text("연결 확인 중")

    page.clock.fast_forward(9000)
    expect(button).to_be_enabled()
    expect(button).to_have_text("다시 연결")
    expect(page.locator("#loginError")).to_contain_text("서버에 연결하지 못했어요")
    pending[0].abort()

    button.click()
    expect(button).to_be_enabled()
    expect(button).to_contain_text("로그인")
    expect(page.locator("#loginError")).to_be_hidden()
    assert not errors, errors
    page.close()


def main() -> None:
    """Verify the deployed Studio sign-in and sign-out flows in Chromium."""
    credentials = dotenv_values("private/web-access.env", interpolate=False)
    output = Path("tmp/studio-login-browser")
    output.mkdir(parents=True, exist_ok=True)
    errors, sent = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True, args=["--no-proxy-server", "--enable-unsafe-swiftshader"]
        )
        check_session_retry(browser, credentials["PUBLIC_URL"])
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(
            "sessionStorage.setItem('persona-studio.demo-session.v1', 'forged-profile');"
        )

        def sent_frame(payload):
            try:
                sent.append(json.loads(payload).get("type"))
            except (ValueError, TypeError):
                pass

        def observe(page):
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("websocket", lambda socket: socket.on("framesent", sent_frame))

        page = context.new_page()
        observe(page)
        response = page.goto(credentials["PUBLIC_URL"], wait_until="domcontentloaded")
        assert response.status == 200 and "www-authenticate" not in response.headers
        expect(page.locator("#loginSubmit")).to_be_enabled()
        expect(page.locator("#loginView")).to_be_visible()
        expect(page.locator("#workspaceView")).to_be_hidden()
        assert page.evaluate("window.isSecureContext")
        page.screenshot(path=str(output / "login-desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        button = page.locator("#loginSubmit").bounding_box()
        assert button["y"] >= 0 and button["y"] + button["height"] <= 844
        page.screenshot(path=str(output / "login-mobile.png"))
        page.set_viewport_size({"width": 1440, "height": 900})

        page.locator("#loginUsername").fill(credentials["TEAM_USERNAME"])
        page.locator("#loginPassword").fill("incorrect-password")
        page.locator("#loginSubmit").click()
        expect(page.locator("#loginError")).to_contain_text("아이디 또는 비밀번호")
        expect(page.locator("#workspaceView")).to_be_hidden()
        page.locator("#loginPassword").fill(credentials["TEAM_PASSWORD"])
        page.locator("#loginSubmit").click()
        expect(page.locator("#workspaceView")).to_be_visible()
        expect(page.locator("#profileName")).to_have_text(credentials["TEAM_USERNAME"])
        expect(page.locator("#loginPassword")).to_have_value("")
        assert "studio_session" not in page.evaluate("document.cookie")
        cookie = next(
            item
            for item in context.cookies()
            if item["name"] == "__Host-studio_session"
        )
        assert (
            cookie["secure"] and cookie["httpOnly"] and cookie["sameSite"] == "Strict"
        )
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#workspaceView")).to_be_visible()
        expect(page.locator("#profileName")).to_have_text(credentials["TEAM_USERNAME"])

        other = context.new_page()
        observe(other)
        other.goto(credentials["PUBLIC_URL"], wait_until="domcontentloaded")
        expect(other.locator("#workspaceView")).to_be_visible()
        page.locator('a[href*="mao"][href*="chat"]').first.click()
        frame = page.frame_locator("#studioFrame")
        expect(frame.locator("#sendButton")).to_be_enabled(timeout=30_000)
        expect(frame.locator('#avatarCanvas[data-loaded="true"]')).to_have_attribute(
            "data-frames", re.compile(r"^[1-9]\d*$"), timeout=20_000
        )
        page.screenshot(path=str(output / "authenticated-studio.png"))
        other.locator("#logoutButton").click()
        expect(other.locator("#loginView")).to_be_visible()
        expect(page.locator("#loginView")).to_be_visible(timeout=10000)
        expect(page.locator("#workspaceView")).to_be_hidden()
        assert context.request.get(credentials["PUBLIC_URL"] + "/docs").status == 401
        assert not errors, errors
        assert not any(
            kind in ("text-input", "mic-audio-end", "ai-speak-signal") for kind in sent
        )
        report = {
            "public_login_without_basic_auth": True,
            "session_check_timeout_and_retry_without_random_uuid": True,
            "forged_storage_rejected": True,
            "incorrect_password_rejected": True,
            "cookie_login_and_reload": True,
            "live2d_and_websocket": True,
            "cross_tab_logout": True,
            "mobile_overflow": False,
            "javascript_errors": errors,
            "model_api_calls": 0,
        }
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2)
        )
        print(json.dumps(report, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
