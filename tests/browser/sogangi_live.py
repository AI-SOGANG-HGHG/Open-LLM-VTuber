"""Opt-in Gemini/TTS playback and history recovery; one request, or two with --memory."""

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Allow one real LLM request"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--memory",
        action="store_true",
        help="Allow a second request to verify recall after reloading",
    )
    modes.add_argument(
        "--expression",
        action="store_true",
        help="Require a joy-tagged reply and semantic expression during actual audio playback",
    )
    parser.add_argument("--avatar", choices=["svg", "live2d"], default="svg")
    args = parser.parse_args()
    if not args.live:
        parser.error(
            "Pass --live to enable a real LLM/TTS request; it may use API quota."
        )
    output = Path(
        "tmp/sogangi-browser/live2d-chat"
        if args.avatar == "live2d"
        else "tmp/sogangi-browser/redesign"
    )
    output.mkdir(parents=True, exist_ok=True)
    frames, errors = [], []
    result = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ.get(
                "SOGANGI_BROWSER",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            ),
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                *(["--enable-unsafe-swiftshader"] if args.avatar == "live2d" else []),
            ],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        def received(payload):
            item = json.loads(payload)
            frames.append(
                {
                    "type": item.get("type"),
                    "request_id": item.get("request_id"),
                    "conf_uid": item.get("conf_uid"),
                    "history_uid": item.get("history_uid"),
                }
            )

        page.on("websocket", lambda socket: socket.on("framereceived", received))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("""
          window.__audioChecks=[];
          const nativePlay=HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play=function(...args){
            if(!this.__observed){this.__observed=true;
              for(const type of ['playing','ended','error'])
                this.addEventListener(type,()=>window.__audioChecks.push({type,time:performance.now()}));
            }
            return nativePlay.apply(this,args);
          };
        """)
        try:
            page.goto(
                os.environ.get("SOGANGI_BASE_URL", "http://localhost:12393")
                + (
                    "/web-tool/sogangi/?avatar=live2d"
                    if args.avatar == "live2d"
                    else "/web-tool/sogangi/?avatar=svg"
                ),
                wait_until="domcontentloaded",
            )
            page.wait_for_function(
                "!document.querySelector('#sendButton').disabled", timeout=60000
            )
            page.wait_for_function(
                "expected=>document.querySelector('#mascot').dataset.renderer===expected",
                arg="live2d" if args.avatar == "live2d" else "svg-parts",
                timeout=45000,
            )
            page.evaluate("""() => {
              window.__maxMouth=0;
              window.__maxCoreMouth=0;
              const canvas=document.querySelector('#avatarCanvas');
              new MutationObserver(()=>{
                window.__maxCoreMouth=Math.max(window.__maxCoreMouth,Number(canvas.dataset.appliedMouth)||0);
              }).observe(canvas,{attributes:true,attributeFilter:['data-applied-mouth']});
              window.__expressionChecks=[];
              new MutationObserver(()=>{
                window.__maxMouth=Math.max(window.__maxMouth,Number(document.querySelector('#mascot').dataset.mouthOpen)||0);
                window.__expressionChecks.push(document.querySelector('#mascot').dataset.expression);
              }).observe(document.querySelector('#mascot'),{attributes:true,attributeFilter:['data-mouth-open','data-expression']});
            }""")
            # No name hint: the answer must come from the selected persona.
            page.locator("#messageInput").fill(
                "너는 누구야? 네 이름을 소개해 줘. 그리고 내가 가장 좋아하는 색은 민트색이야. 기억해 줘."
                if args.memory
                else "네 이름을 포함해서 한 문장으로 밝게 인사해 줘. 표정 태그 [joy]를 맨 앞에 붙여 줘."
                if args.expression
                else "너는 누구야? 이름을 포함해 한 문장으로 짧게 소개해 줘."
            )
            page.locator("#sendButton").click()
            page.wait_for_function("!document.querySelector('#stopButton').disabled")
            page.wait_for_function(
                "document.querySelector('#stopButton').disabled", timeout=100000
            )
            result = {
                "avatar": args.avatar,
                "renderer": page.locator("#mascot").get_attribute("data-renderer"),
                "max_core_mouth_open": page.evaluate("window.__maxCoreMouth"),
                "final_core_mouth_open": page.locator("#avatarCanvas").get_attribute(
                    "data-applied-mouth"
                ),
                "assistant": page.locator(
                    ".message.assistant .message-body"
                ).all_text_contents(),
                "timing": page.locator("#timing").inner_text(),
                "audio": page.evaluate("window.__audioChecks"),
                "max_mouth_open": page.evaluate("window.__maxMouth"),
                "expressions_seen": sorted(
                    set(page.evaluate("window.__expressionChecks")) - {None}
                ),
                "final_mouth_open": page.locator("#mascot").get_attribute(
                    "data-mouth-open"
                ),
                "notice": page.locator("#noticeText").inner_text(),
                "page_errors": errors,
                "selected_sogangi": any(
                    f["conf_uid"] == "sogangi-prototype-v1" for f in frames
                ),
            }
            kinds = [frame["type"] for frame in frames]
            result["synthesis_complete_events"] = kinds.count("backend-synth-complete")
            result["text_before_audio"] = (
                "text-response" in kinds
                and "audio" in kinds
                and kinds.index("text-response") < kinds.index("audio")
            )
            ids = {
                frame["request_id"]
                for frame in frames
                if frame["type"] in ("text-response", "audio", "backend-synth-complete")
            }
            result["correlated_request_ids"] = len(ids) == 1 and None not in ids
            assert not errors, "JavaScript exception"
            assert result["selected_sogangi"], "Wrong persona selected"
            assert "서강이" in " ".join(result["assistant"]), "Missing persona identity"
            assert any(event["type"] == "playing" for event in result["audio"]), (
                "No real audio playback"
            )
            assert any(event["type"] == "ended" for event in result["audio"]), (
                "Audio did not finish"
            )
            assert result["max_mouth_open"] > 0.12, "No visible lip sync"
            assert result["final_mouth_open"] == "0.00", "Mouth did not close"
            assert result["synthesis_complete_events"] == 1, (
                "Duplicate synthesis completion"
            )
            assert result["text_before_audio"] and result["correlated_request_ids"]
            if args.avatar == "live2d":
                assert result["renderer"] == "live2d", "Native renderer fell back"
                assert result["max_core_mouth_open"] > 0.12, (
                    "Native Core mouth was not driven by audio"
                )
                assert float(result["final_core_mouth_open"]) == 0, (
                    "Native Core mouth stayed open"
                )
            if args.expression:
                assert "joy" in result["expressions_seen"], (
                    "Joy expression was not applied during the real reply"
                )
            previous_answer = result["assistant"]
            initial_uid = next(
                frame["history_uid"]
                for frame in frames
                if frame["type"] == "new-history-created"
            )
            page.locator("#messageInput").fill("새로고침 후 남길 초안")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function(
                "!document.querySelector('#sendButton').disabled", timeout=60000
            )
            assert (
                page.locator(".message.assistant .message-body").all_text_contents()
                == previous_answer
            ), "Saved reply changed after refresh"
            assert (
                page.locator("#messageInput").input_value() == "새로고침 후 남길 초안"
            ), "Draft lost after refresh"
            assert (
                sum(frame["type"] == "new-history-created" for frame in frames) == 1
            ), "Refresh created another history"
            assert any(
                frame["type"] == "history-data" and frame["history_uid"] == initial_uid
                for frame in frames
            ), "Wrong history restored"
            result["real_history_restored_after_reload"] = True
            result["draft_restored_after_reload"] = True
            if args.avatar == "live2d":
                page.wait_for_function(
                    "document.querySelector('#mascot').dataset.renderer==='live2d'",
                    timeout=45000,
                )
                assert (
                    float(
                        page.locator("#avatarCanvas").get_attribute(
                            "data-applied-mouth"
                        )
                    )
                    == 0
                )
                result["native_renderer_restored_after_reload"] = True
            if args.memory:
                page.locator("#messageInput").fill(
                    "내가 가장 좋아하는 색은 뭐야? 짧게 답해 줘."
                )
                page.locator("#sendButton").click()
                page.wait_for_function(
                    "!document.querySelector('#stopButton').disabled"
                )
                page.wait_for_function(
                    "document.querySelector('#stopButton').disabled", timeout=100000
                )
                recalled = page.locator(
                    ".message.assistant .message-body"
                ).last.inner_text()
                result["recall_after_reload"] = recalled
                result["memory_recalled_after_reload"] = "민트" in recalled
                assert result["memory_recalled_after_reload"], (
                    "Model did not recall the saved fact after refresh"
                )
            result["passed"] = True
        except Exception as error:
            result["passed"] = False
            result["failure"] = type(error).__name__ + ": " + str(error).splitlines()[0]
            raise
        finally:
            page.screenshot(path=str(output / "live-conversation.png"), full_page=True)
            (output / "live-result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(result, ensure_ascii=True), flush=True)
            browser.close()


if __name__ == "__main__":
    main()
