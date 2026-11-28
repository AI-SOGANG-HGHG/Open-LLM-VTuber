
# Config Template

This directory contains the default configuration files. One of the configuration file, `conf.default.yaml` by default, will be copied to the root directory of this project as `conf.yaml`.

The default chat provider is `openai_llm` with `gpt-5.4-mini`. For a team Linux server, copy `conf.studio.yaml` to `conf.yaml` for Korean Edge TTS and CPU SenseVoice. The launcher reads `OPENAI_API_KEY` from the private `.env`. For a direct `run_server.py` launch, set the key in the process environment. See the [Linux server guide](../docs/linux-server.md).

The team example `conf.gemini.example.yaml` uses Gemini API, CPU SenseVoice, and Korean Edge TTS. Copy it to the local, ignored `conf.yaml` and set `GEMINI_API_KEY` before starting the server. See [Windows setup](../docs/local-gemini-setup.md).

