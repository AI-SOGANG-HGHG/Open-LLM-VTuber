# Sogangi browser checks

The production Studio form login has a separate no-model-call check:
`python tests/browser/studio_login.py`. Run it from the repository root in the
optional Playwright environment with `python-dotenv` installed and an installed
Chromium. It reads the private `private/web-access.env` file without printing
credentials. It covers public login without Basic Auth, wrong-password errors,
forged sessionStorage, secure cookies, refresh, mobile overflow, authenticated
Mao rendering/WebSocket, and logout across two tabs. It writes screenshots and
a credential-free report under `tmp/studio-login-browser/`.

The normal Python checks run with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The browser checks use an optional Playwright environment and an installed Chrome binary. They load the actual page from a running local server, replace only the chat WebSocket with a fixture, and make no LLM/TTS API calls.

```powershell
.\tmp\tools\uv.exe venv tmp/browser-tools --python .venv/Scripts/python.exe
.\tmp\tools\uv.exe pip install --python tmp/browser-tools/Scripts/python.exe playwright
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_smoke.py
```

Set `SOGANGI_BROWSER` to another Chromium browser executable or `SOGANGI_BASE_URL` to another local server address if needed. The default browser is `C:\Program Files\Google\Chrome\Application\chrome.exe` and the default server is `http://localhost:12393`.

Run `python tests/browser/ivory_crown.py` to verify the Kang Iseo default profile, workspace migration, and creation from Discover. The tests load Kang Iseo's exported Cubism model and compare rendered eye, mouth, expression, tilt and breathing changes. Studio playback uses fixture audio and checks mouth closure on interruption. The fallback cases cover WebGL loss, Canvas and static portraits, retry, and mobile layout.

The 19 regressions cover text before audio, duplicate completion, mute, stale responses after interruption, reconnect, HTML-safe display, history restoration, SVG fallback, audio-driven mouth movement, microphone-track cleanup, greeting/reset, reduced motion and the mobile composer after long replies. They also check sentence-aligned expression timing and expression reset after interruption/new chat. The microphone uses Chrome's fake device, not the user's hardware.

The 14 product checks cover saved preferences, refresh and automatic reconnect, draft preservation, failed-question recovery, corrupt/blocked browser storage, real browser volume/rate, history search, UTF-8 downloads and the actual artwork handoff ZIP/PSD header/hash. They also run 100 fixture turns, 10 reconnects and a 1,000-item history list without model calls. These are accelerated regressions, not a multi-hour endurance test.

```powershell
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_product.py
# All code/backend/browser/viewport checks, no model calls:
powershell -ExecutionPolicy Bypass -File tools/check_sogangi.ps1 -WithBrowser
```

Five additional checks use the real Mao and Sogangi minimum MOC3 models and local Cubism Core/WebGL, not a mock. They test rendering, mouth control, reload texture survival, selected motion without audio, invalid-model recovery and the rigging map. The Sogangi check verifies the actual build hash, eye/mouth pixel changes, exact neutral restoration, mobile layout and the disabled unbound head control. The existing frontend Core and both model folders are required. These checks do not validate live-audio synchronization or full head/body rigging.

```powershell
.\tmp\browser-tools\Scripts\python.exe tests/browser/live2d_preview.py
```

Four art-review checks use the actual SVG/PSD assets. They compare neutral pixels, validate the separate candidate download and baseline provenance, exercise mobile zoom, and measure rendered eye/mouth continuity around the former switch thresholds. The grouped import download check also verifies 24 layer paths, three parameter targets and default visibility, pixel-reader provenance, and non-overlapping single-atlas placement. They do not certify anatomy or Cubism import. The optional art environment is needed only to regenerate the assets, not to run these browser checks.

```powershell
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_art_review.py
```

Thirteen Live2D conversation checks load the actual Sogangi expression MOC/Core inside the main page and retain the real HTML audio clock with fixture WAV/messages. They cover rendered mouth pixel changes and exact closure, sentence-aligned joy eyes and muted text, stop/new chat, mute, delayed MOC loading, switching modes during playback without restarting it or requests, invalid-manifest fallback, context loss/retry, and saved-mode/history/draft recovery. The movement case checks actual Core head tracking/return and breathing, app/OS reduced motion, exact frozen pixels and retained audio lip sync. Greeting cases check one-shot completion, ignored repeated clicks, no chat request, simultaneous speech and cancellation on reduce/stop/new chat/mode changes without replay. These checks do not call Gemini or TTS services.

```powershell
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_live2d_chat.py
```

Two composed-grid checks compare neutral pixels across the preserved facial, head/breath and greeting models. They combine face/head/breath controls, measure large silhouette components over 12 arm/breath poses to detect detachment, and require exact reset. Run `tests/browser/sogangi_motion.py`; captures are in `tmp/sogangi-browser/motion/` and `tmp/sogangi-browser/greeting/`. They use actual MOC/Core rendering, with no API calls or deformer/3D rigging certification. Connected components do not replace visual shoulder/anatomy review.

Two expression checks in `tests/browser/sogangi_expressions.py` require exact neutral preservation/reset, independent blink/lip controls under anger/surprise, and real exp3 file playback without mouth bindings. Two additional chat cases check sentence order, muted tags, interruption, SVG fallback/recovery, reduced motion and unsupported-tag fallback.

The full browser suite now has 59 regressions (19 conversation + 14 product + 5 Cubism + 4 art + 2 motion/arm + 2 expression + 13 Live2D conversation), plus the six viewport captures below.

Capture six viewport sizes, including a small phone and landscape, without LLM calls:

```powershell
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_visual.py
```

The capture script explicitly selects SVG to preserve comparable artwork/greeting baselines; Live2D desktop/mobile captures are in `tmp/sogangi-browser/live2d-chat/`. It checks overflow, the mobile/landscape composer and stage-note clipping. Review the screenshots in `tmp/sogangi-browser/redesign/`; geometry checks do not judge visual quality.

A separate opt-in check makes **one real LLM request**, uses configured TTS and observes actual browser audio playback plus mouth movement. It consumes API quota. It uses a synthetic identity question, not private history. Without `--live` it refuses to run:

```powershell
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_live.py --live
# Two requests: store a synthetic preference, reload, then ask the model to recall it.
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_live.py --live --memory
# One request: explicitly verify a joy-tagged reply, real audio and SVG expression.
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_live.py --live --expression
# One request: the same check with actual Cubism Core mouth values and renderer recovery.
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_live.py --live --avatar live2d --expression
```

The default live check also reloads the page and verifies that the same server history and draft return. `--avatar live2d` additionally requires actual Core mouth movement, final closure and the Live2D renderer after reload. The CLI defaults to explicitly testing SVG; the app itself now defaults to Live2D. SVG fixture regressions seed a saved SVG choice, while the Live2D recovery check also verifies a fresh default and persistence of a URL-selected mode through the normal URL. `--memory` adds one request to verify the restored Agent's recall, for two requests total. These checks do not verify physical speaker output, real microphone hardware, full head/body rigging, general persona consistency or long-term latency. The separate persona tool and its limits are described in `docs/sogangi-persona-evaluation.md`.
