# Hybrid Backend Plan (rgi-group fork)

> Goal: one MCP tool surface, two interchangeable engines. Stable official spine by
> default; real NotebookLM on demand. Called by Antigravity / Claude / Cursor / OpenCode.

## Why this fork exists
Upstream (`jacob-bd/notebooklm-mcp-cli`) drives **consumer NotebookLM** via its
undocumented internal web API + cookie auth (`core/client.py`, httpx + CDP login).
That's the *only* way to reach real NotebookLM — there is **no official consumer API**.
It's powerful but brittle: a Google UI change can break it. We fork so a break is a
bug **we** patch, and we add a second, stable backend on official Google SDKs.

## Architecture — the seam
```
mcp/tools/*.py   →   services/*.py(client, …)   →   BACKEND
                              ↑ the `client` arg is the seam
```
`services/studio.py` already takes a `client` and calls `client.create_audio_overview()`,
`client.poll_studio_status()`, etc. We make `client` a **protocol** with two impls.

### Backends
| Backend | Engine | Auth | Covers |
|---|---|---|---|
| `notebooklm` (existing) | NotebookLM internal web API | Google cookie (`nlm login`) | ALL artifacts: audio, video, infographic, slide_deck, mind_map, quiz, flashcards, report, data_table |
| `official` (NEW) | `google-genai` SDK | `GEMINI_API_KEY` **or** Vertex ADC (GCP) | **audio** (multi-speaker TTS podcast), **report/query** (Files API + grounding). Optional: **video** → Veo. Others → `UnsupportedOnBackend` (optional auto-fallback to `notebooklm`). |

### Selection
- Env: `NOTEBOOKLM_BACKEND=notebooklm|official` (default `notebooklm` for drop-in compat).
- Per-call override param on tools (future).
- `NOTEBOOKLM_OFFICIAL_FALLBACK=1` → unsupported official ops transparently use `notebooklm`.

### Official backend mapping
- **audio (podcast)** → `gemini-2.5-flash-preview-tts` (or newest Flash TTS), multi-speaker 2-host config. Returns audio bytes → upload to `gs://bingo-codes-blog/` → return URL. *This closes the pipeline gap (no manual NotebookLM UI export).* 
- **report / query (grounded)** → upload sources via Files API, ground generation on them, return markdown.
- **video** (optional) → Veo (`veo-3.1-generate-preview`) via `client.models.generate_videos()` — reuses the existing Bingo pipeline pattern.
- Async studio model: official ops are mostly synchronous; `poll_studio_status` returns `completed` immediately for official artifacts (with a small in-memory job table for TTS/Veo long-runs).

## Phases
1. **Scaffold** (this commit): `backends/` package — `base.py` (Protocol), `factory.py` (selector), `official.py` (skeleton + NotImplemented), `errors.py` (`UnsupportedOnBackend`). No behavior change; default stays `notebooklm`.
2. **Official audio (TTS podcast)** — implement `create_audio_overview` + status + download on `official`; GCS upload helper. Smoke-test end to end.
3. **Official report/query** — Files API grounding for `report` + chat/query.
4. **Factory wiring** — route `services/*` through the factory; `NOTEBOOKLM_BACKEND` + fallback flag; per-call override.
5. **Video (optional)** — Veo path.
6. **Tests + docs** — unit tests per backend, update README, ship to PyPI-private or install from git.

## Credentials needed before phase 2 is testable
- `GEMINI_API_KEY` (aistudio.google.com, pay-as-you-go) — simplest, OR
- **Vertex AI** via GCP ADC (`gcloud auth application-default login`) — bills to the GCP project, keeps billing in one place. Chris already has gcloud authed + `gs://bingo-codes-blog/`.

## Consumers
All four agents call this one MCP server (stdio or http):
Antigravity (`McpStdioServer`), Claude Code (`~/.claude.json`), Cursor (`~/.cursor/mcp.json`), OpenCode (`~/.config/opencode/opencode.json`).
