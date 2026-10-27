# Frontend team guide

- Follow the root `AGENTS.md` and `docs/frontend-development.md`.
- This is ordinary source in the team repository, not a Git submodule.
- Web UI code is in `src/renderer/src/`; inspect nearby components and hooks before editing.
- For web development use `npm ci --ignore-scripts`, then `npm run dev:web`.
- Verify web builds with `npm run build:web`. Record inherited failures from `npm run typecheck:web` rather than claiming all checks passed.
- `npm run lint` and `npm run lint:fix` both modify files. Use direct ESLint without `--fix` for a read-only check.
- Keep upstream and SDK licenses/notices. Do not reformat bundled SDKs as part of unrelated work.
- Do not commit generated `node_modules/`, `dist/`, or `out/` contents.
- Electron commands in `CLAUDE.md` require separate setup; current team integration targets the browser.
