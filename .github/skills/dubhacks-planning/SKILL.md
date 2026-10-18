---
name: dubhacks-planning
description: Create or revise a deadline-driven, implementation-ready engineering plan for this DubHacks 2026 Photon + Grok + FastAPI fragrance shopping assistant. Use when deciding MVP scope, interfaces, parallel tasks, integration fallbacks or demo readiness.
argument-hint: State the desired plan update or current blocker
user-invocable: true
disable-model-invocation: true
---

# DubHacks planning workflow (no code edits)

1. Read `AGENTS.md` and `COPILOT_PLAN_TEXT.txt` from the repository root, then `docs/PROJECT_BRIEF.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/SPRINT_PLAN.md`, `docs/IMPLEMENTATION_TASKS.md`.
2. Discover actual repository contents. Explicitly distinguish the plan's **proposed** file layout from **existing** files. Do not infer integrations from filenames.
3. Treat Photon 2.0 Beta access, webhook verification and outbound send schemas as **unverified** until checked against the team's real credentials and current documentation. Never substitute legacy Photon products' contracts.
4. Produce prioritized P0 file-by-file tasks, interfaces, owners, sequential integration steps, testing and live proof checkpoints. Label P1 for deferred price comparison and deterministic wallet rewards.
5. Include a compact triage plan for absent Photon access (local debug endpoint and clearly labeled mock; sponsor track not qualified until real channel integration), absent search provider, or absent Grok credits.
6. Give a human-readable list of decisions requiring approval; do not modify the repository or start implementation unless a human explicitly requests that next step.
