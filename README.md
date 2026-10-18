# DubHacks '26 — AI Shopping Assistant Agent Kit (v2)

**Project:** SMS-first, evidence-backed shopping decision assistant for fragrance purchases.
**Track recommendation:** VISA: Reimagine Shopping; **sponsored side-track candidate:** Photon 2.0 Messaging Agent.
**Status:** Planning/instructions only. This kit does **not** implement working Photon, Grok, or Tavily integrations.
**Current phase:** Pre-implementation planning / contract gate.
**Immediate team decision:** Lock title/sponsor track choices and confirm provider access/docs (Photon, Grok, and one research provider) before coding.

## Put these files in your repository

Merge the contents of this directory into the **root of your hackathon repository**. Preserve the `.github/` directory. If an existing file has the same name, **review and merge**; do not overwrite teammates' work.

```
AGENTS.md
COPILOT_PLAN_TEXT.txt                      # paste into Copilot Plan; standalone and complete
.github/copilot-instructions.md            # repo instructions for GitHub Copilot
.github/agents/tech-lead.agent.md          # custom planning agent
.github/agents/builder.agent.md            # scoped implementation agent
.github/agents/evidence-reviewer.agent.md  # claims/security/QA review
.github/prompts/dubhacks-plan.prompt.md    # VS Code Local harness /dubhacks-plan
.github/skills/dubhacks-planning/SKILL.md  # Copilot harness /dubhacks-planning

docs/PROJECT_BRIEF.md
 docs/ARCHITECTURE.md
 docs/API_CONTRACTS.md
 docs/IMPLEMENTATION_TASKS.md
 docs/SPRINT_PLAN.md
 docs/TRACK_DECISION.md
 docs/SUBMISSION_CHECKLIST.md
 docs/INTEGRATION_RUNBOOK.md
```

## Start now — two ways to get a Copilot implementation plan

**Universal (works regardless of harness):** In VS Code Copilot Chat, select **Plan** if available, or `tech-lead`, and paste all text from `COPILOT_PLAN_TEXT.txt`. Ask for a file-by-file plan **without editing source**.

**Reusable command:**
- VS Code **Local harness**: run `/dubhacks-plan` from `.github/prompts/dubhacks-plan.prompt.md` (prompt files are Local-harness-only in the current VS Code docs).
- VS Code **Copilot harness**: run `/dubhacks-planning` from `.github/skills/dubhacks-planning/SKILL.md`, or invoke the `tech-lead` custom agent.
- **Codex**: open the repo, ensure root `AGENTS.md` is visible, then paste the request from `COPILOT_PLAN_TEXT.txt`. `AGENTS.md` is recognized by Codex; Copilot `.agent.md` files are **not** automatically equivalent to Codex's role system.

Read `docs/INTEGRATION_RUNBOOK.md` for integration blockers and the order to verify services.

## Product MVP, not a generic full-stack app

One real customer journey: **SMS with fragrance URL -> Photon inbound -> FastAPI -> Grok request classification -> a single research provider -> evidence validation -> deterministic seller-risk decision -> response through Photon**.

A developer-only `POST /api/v1/evaluate` endpoint runs the same pipeline *without* Photon and is essential for early local testing. A true Photon success requires an end-to-end delivered message, not a mocked send.

Credit-card optimization, exact-match multi-merchant price comparison, Redis, PostgreSQL, and multi-agent orchestration are optional until P0 works.

## Implementation gate checks

1. Identify **real** Photon 2.0 access/docs for the account; do not copy legacy Photon webhook field names or signature headers without verifying against the version actually used.
2. Confirm **live** Grok API account/model and choose **one** research path: Tavily or native Grok Web Search. Both have public documentation; your team must verify actual API access/credits.
3. Finalize the backend request/response interfaces (`docs/API_CONTRACTS.md`) before parallel implementation.
4. Human-own the 10:30 PM Saturday **mandatory draft** and 10:00 AM Sunday **final** (PDT). Aim earlier to avoid upload problems.
5. Demo evidence should reflect genuinely run integrations. **Mark fixtures as fixtures.**

## Sources consulted (documentation, not proof of your credentials)

- Project brief supplied by team, October 17, 2026.
- Official DubHacks Hacker Guide supplied with team workspace.
- VS Code: https://code.visualstudio.com/docs/agent-customization/custom-agents
- VS Code prompt files: https://code.visualstudio.com/docs/agent-customization/prompt-files
- VS Code agent skills: https://code.visualstudio.com/docs/agent-customization/agent-skills
- Codex `AGENTS.md` example: https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex
- xAI tool overview: https://docs.x.ai/developers/tools/overview
- xAI web search: https://docs.x.ai/developers/tools/web-search
- xAI structured outputs: https://docs.x.ai/developers/model-capabilities/text/structured-outputs
- Tavily search: https://docs.tavily.com/documentation/api-reference/endpoint/search
- Tavily extract: https://docs.tavily.com/documentation/api-reference/endpoint/extract
- Photon 2.0 announcement: https://photon.codes/blog/introducing-photon-2.0
- Photon public API spec (check compatibility with your beta setup): https://github.com/photon-hq/api
