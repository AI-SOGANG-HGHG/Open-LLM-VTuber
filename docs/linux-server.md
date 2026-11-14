# Linux server with Gemini

Use the latest platform code and its pinned frontend submodule. The launcher
reads `GEMINI_API_KEY` from the repository's private `.env` file and passes it
to the existing configuration loader. It does not execute the file as shell code.

## Key and configuration

Create the local files once; preserve existing files if they already exist:

```bash
umask 077
test -e .env || cp .env.example .env
test -e conf.yaml || cp config_templates/conf.gemini.example.yaml conf.yaml
chmod 600 .env conf.yaml
```

Edit `.env` and enter the key after `GEMINI_API_KEY=`. Save the file, without
putting the key into a shell command, shared document, or chat message. Both
`.env` and `conf.yaml` are ignored by Git and Docker. The key remains on this
server between restarts; restart the application after editing it.

Leave `${GEMINI_API_KEY}` in `conf.yaml`. The model name, Korean Edge TTS voice,
and CPU SenseVoice settings come from the existing Gemini template. Model
availability and API quota must be checked with the configured account.

## Runtime and launch

The standard project setup is `uv sync --locked`, FFmpeg on PATH, and
`git submodule update --init --recursive`. For the CPU Gemini configuration,
GPU inference dependencies are not required by the selected engines. To install
only the selected runtime and regression-check dependencies on Linux:

```bash
uv venv .venv --python 3.12
mkdir -p tmp
uv export --frozen --no-hashes --no-emit-project --format requirements-txt \
  --output-file tmp/locked-requirements.txt --quiet
uv pip install --python .venv/bin/python -c tmp/locked-requirements.txt \
  loguru numpy scipy pydub openai anthropic fastapi mcp letta-client \
  langdetect pysbd pyyaml ruamel-yaml chardet tomli ruff websockets \
  requests soundfile jinja2 python-dotenv edge-tts sherpa-onnx onnxruntime
```

Install FFmpeg separately. This server uses the FFmpeg executable packaged by
`imageio-ffmpeg==0.8.1`, linked as `.venv/bin/ffmpeg`; a system FFmpeg on PATH
also works. To prepare the bundled executable:

```bash
uv pip install --python .venv/bin/python imageio-ffmpeg==0.8.1
.venv/bin/python -c 'from pathlib import Path; import imageio_ffmpeg; p=Path(".venv/bin/ffmpeg"); p.exists() or p.symlink_to(imageio_ffmpeg.get_ffmpeg_exe())'
```

This reduced environment does not verify the other optional providers.
The initial CPU model download is about 239 MB for `model.int8.onnx`
and 316 KB for `tokens.txt`, obtained from the SenseVoice distribution at
`csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17` on Hugging Face.

```bash
bash start-server.sh --check
bash start-server.sh
```

`--check` validates configuration and selected engine imports without calling
Gemini, initializing models, or testing audio. First startup downloads the
SenseVoice model if it is missing. The configured application is served at
`http://localhost:12393/web-tool/platform/`. Stop a foreground server with
Ctrl+C. `python tools/platform_preview.py` separately serves only the static
preview on `http://127.0.0.1:12401/platform/`.

The current platform does not implement account authentication. Keep the
backend on loopback while validating it; use an SSH tunnel or authenticated
HTTPS gateway for remote access. HTTPS is needed for browser microphone use
outside localhost. A shell launch alone does not configure automatic restart
or startup after a reboot.

## User service

For a checkout at `~/Open-LLM-VTuber`, install the provided user service after
configuration and live checks pass:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/open-llm-vtuber.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now open-llm-vtuber.service
systemctl --user status open-llm-vtuber.service
```

Restart after editing `.env`: `systemctl --user restart open-llm-vtuber.service`.
Stop with `systemctl --user stop open-llm-vtuber.service`. The service restarts
on runtime failures, but missing key/configuration exits do not enter a restart
loop. User services need lingering enabled for startup before login and
continued operation after logout; check with `loginctl show-user "$USER" -p Linger`.

## Observed on the Ubuntu server, 2026-11-14

- Based on platform commit `290e28d`; Python 3.12.3, CPU SenseVoice, Edge TTS
  7.3.1, and configured Gemini `gemini-3.5-flash-lite`.
- Ruff passed. All 39 existing backend regressions passed, including MP3
  decoding with the prepared FFmpeg executable.
- The private `.env` key produced a real Gemini response. Studio HTML, its
  embedded runtime, Mao model metadata, and rendering script returned HTTP 200.
- Applying a synthetic Studio persona and sending one text request returned
  streamed text, non-silent WAV audio, correlated request IDs, and one synthesis
  completion. Feeding that audio back at 16 kHz returned an ASR transcription,
  another real response, and WAV audio. This checked two live conversation turns.
- The user service was active with zero restarts; user lingering was enabled.
  Reboot recovery was configured, not tested by rebooting the server.
- Physical microphone/speaker output, browser rendering and lip sync, and
  external HTTPS access were not verified in this server check.
