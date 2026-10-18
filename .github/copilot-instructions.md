# DubHacks project instructions for GitHub Copilot

`AGENTS.md` is the shared instruction source for all coding tools. Before implementation, read `docs/OWNERSHIP.md`, the assigned guide under `docs/skills/`, and `docs/AGENT_HANDOFF.md`. Follow the explicit session assignment and exclusive file ownership. Use separate checkouts/worktrees for concurrent edits.

Preserve tracked and untracked changes. Never reset or clean Git state, bulk-restore files, force checkout, or delete another agent's work to make `git status` clean without explicit authorization for that action. Shared models belong to D; application wiring and integration belong to A. Copilot agent definitions do not configure other tools.

Read the root `AGENTS.md` and relevant `docs/*.md` before nontrivial edits. This is **a fragrance shopping decision assistant with both Photon messaging and a Chrome extension with an animated on-page pet**. Current extension scope and implementation status are in `docs/EXTENSION_SCOPE.md`; Both channels are core scope and share one backend. Backend: Python/FastAPI/Pydantic. Planned providers: Photon 2.0, Grok, and one of Tavily or native Grok Web Search.

When the user asks to **plan**, inspect the repository and produce tasks, file paths, interfaces, acceptance tests, dependencies, and a deadline-aware critical path **without coding or touching files** unless requested. Use `COPILOT_PLAN_TEXT.txt` as the detailed planning specification.

When the user asks to **implement**, limit edits to assigned paths; run focused tests; never invent Photon beta request/response payloads or signatures; keep API keys server-side; ensure model claims cite actual retrieved URLs; keep risk classifications deterministic and conservatively handle insufficient evidence. Show mock/demo output only if clearly labeled.

Prioritize user-triggered pet -> backend -> Grok -> Tavily -> evidence -> policy -> cited extension result before price/card rewards or databases. Keep progress states truthful and provider keys server-side. Maintain the tested Photon channel as a core path, including a reproducible bounded launcher and verified replies. If a dependency is unavailable, preserve a real local `/api/v1/evaluate` path and document exactly which provider remains untested. Note submission cutoff, video, public source, and human review before any late refactor.
