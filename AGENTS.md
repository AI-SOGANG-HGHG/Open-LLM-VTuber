# Team project guide

- Start with `README.team.md` and `docs/plan.md`.
- Build the shared persona agent platform: character settings, conversation, memory, session state, and reproducible evaluation of dialogue and behavior. VTuber/broadcasting and Minecraft integrations are in project scope through adapters. Walking/mobile companionship and eight-agent Minecraft matches are later exploratory goals.
- Follow the updated direction in `docs/system-direction.md`. Its architecture and evaluation details are proposals until accepted; the user's stated project scope and deployment decisions take precedence over earlier documents excluding games or broadcasting.
- The first 1–2 weeks focus on existing-code analysis and platform design. Keep proposals, implemented features, and observed verification distinct.
- Use the existing Open-LLM-VTuber modules and inspect nearby code before choosing new module boundaries.
- Keep design documents and related code changes in this repository. The parent persona-platform directory is only a local container.
- Read existing runtime guidance such as `CLAUDE.md`, but confirm commands and paths against current source. Explicit user instructions and team scope take precedence over defaults.
- Do not report dependency setup, model, voice, or avatar success without running the relevant checks.
- Never put API keys or private conversation data in shared documents.
- `origin` is `https://github.com/AI-SOGANG-HGHG/Open-LLM-VTuber.git`; `upstream` is the original repository. Share team changes through origin and keep the original remote for reference and updates.
