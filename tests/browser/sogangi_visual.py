"""Capture the real page at common viewports; chat uses a fixture, no API calls."""

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from sogangi_smoke import ChatFixture


def main():
    output = Path("tmp/sogangi-browser/redesign")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get(
                "SOGANGI_BROWSER",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            ),
            headless=True,
        )
        for name, width, height in [
            ("desktop", 1440, 900),
            ("wide", 1920, 1080),
            ("tablet", 768, 1024),
            ("mobile", 390, 844),
            ("small-mobile", 360, 640),
            ("mobile-landscape", 844, 390),
        ]:
            page = browser.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            fixture = ChatFixture()
            page.route_web_socket("**/client-ws", fixture.connect)
            page.goto(
                os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
                + "/web-tool/sogangi/?avatar=svg",
                wait_until="networkidle",
            )
            page.wait_for_function(
                "document.querySelector('#mascot').dataset.renderer === 'svg-parts'"
            )
            if name == "desktop":
                page.locator("#greetButton").click()
                page.wait_for_timeout(350)
                page.screenshot(path=str(output / "greeting.png"), full_page=True)
            # Freeze secondary motion for comparable still images.
            page.locator("#motionToggle").click()
            page.screenshot(path=str(output / f"{name}.png"), full_page=True)
            layout = page.evaluate("""() => {
              const rect = selector => {
                const {x,y,width,height,bottom,right}=document.querySelector(selector).getBoundingClientRect();
                return {x,y,width,height,bottom,right};
              };
              return {overflow:document.documentElement.scrollWidth>innerWidth,
                pageHeight:document.documentElement.scrollHeight,
                composer:rect('#composer'), stage:rect('.stage'), mascot:rect('#mascotWrap'), note:rect('#mascotNote')};
            }""")
            assert not errors, (name, errors)
            assert not layout["overflow"], (name, layout)
            assert layout["note"]["y"] >= layout["stage"]["y"], (
                name,
                "clipped note",
                layout,
            )
            assert layout["note"]["right"] <= layout["stage"]["right"], (
                name,
                "clipped note",
                layout,
            )
            if width <= 680 or height <= 520:
                assert layout["composer"]["bottom"] < height, (name, layout)
            results.append({"viewport": name, "layout": layout, "errors": errors})
            if name in {"desktop", "mobile", "small-mobile"}:
                page.locator("#settingsButton").click()
                box = page.locator("#settingsDialog").bounding_box()
                assert (
                    box["x"] >= 0
                    and box["y"] >= 0
                    and box["y"] + box["height"] <= height
                ), (name, "settings dialog clipped", box)
                page.screenshot(
                    path=str(output / f"{name}-settings.png"), full_page=True
                )
                page.keyboard.press("Escape")
            page.close()
        browser.close()
    (output / "layout.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"{len(results)} viewport checks passed; captures: {output}")


if __name__ == "__main__":
    main()
