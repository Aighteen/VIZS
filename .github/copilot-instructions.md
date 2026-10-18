# DubHacks project instructions for GitHub Copilot

Read the root `AGENTS.md` and relevant `docs/*.md` before nontrivial edits. This is **an SMS-first fragrance shopping decision assistant**, not a generic React application. Backend: Python/FastAPI/Pydantic. Planned providers: Photon 2.0, Grok, and one of Tavily or native Grok Web Search.

`AGENTS.md` is the shared project instruction source across coding tools. Before implementation, also read `docs/OWNERSHIP.md`, your assigned `docs/skills/packet-*.md`, and `docs/AGENT_HANDOFF.md`. Follow the explicit session assignment and use a separate worktree/checkout for concurrent edits. The packet ownership table refines test ownership; shared models belong to D and application wiring to A. Do not assume Copilot agent definitions configure other tools.

When the user asks to **plan**, inspect the repository and produce tasks, file paths, interfaces, acceptance tests, dependencies, and a deadline-aware critical path **without coding or touching files** unless requested. Use `COPILOT_PLAN_TEXT.txt` as the detailed planning specification.

When the user asks to **implement**, limit edits to assigned paths; run focused tests; never invent Photon beta request/response payloads or signatures; keep API keys server-side; ensure model claims cite actual retrieved URLs; keep risk classifications deterministic and conservatively handle insufficient evidence. Show mock/demo output only if clearly labeled.

Keep P0 SMS -> Photon -> backend -> Grok -> search -> evidence -> decision -> SMS working before price/card rewards or databases. If a dependency is unavailable, preserve a real local `/api/v1/evaluate` path and document exactly which provider remains untested. Note submission cutoff, video, public source, and human review before any late refactor.
