# DubHacks '26 — AI Shopping Assistant Agent Kit (v2)

**Project:** SMS-first, evidence-backed shopping decision assistant for fragrance purchases.
**Track recommendation:** VISA: Reimagine Shopping; **sponsored side-track candidate:** Photon 2.0 Messaging Agent.
**Status:** Packets A-D merged on `feat/packet-a-integration`; 91 offline tests pass. Grok/Tavily adapters exist; default application wiring and live shopping flow remain pending.
**Current phase:** Runtime wiring and end-to-end validation. See [next steps](docs/NEXT_STEPS.md).
**Immediate next step:** A wires the merged components into the application with explicit offline/live configuration. Paid API calls still require instruction. Humans finalize tracks.

## Run the local API

Use Python 3.11+ (tested with 3.12):

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[test]'
.venv/Scripts/python.exe -m uvicorn app.main:app
```

`GET /healthz` performs no external calls. The default `POST /api/v1/evaluate`
returns 503 until the merged contracts and domain components are injected.
`POST /webhooks/photon` returns a local disabled 503; no vendor acknowledgement,
authentication, or retry behavior is assumed.

Integrate by constructing `Contracts(ShoppingRequest, OrchestratorPlan, Assessment)`
and `EvaluationWorkflow(contracts, extract, research, decide, settings)`, then call
`create_app(workflow=workflow)`. The injected async extraction function accepts a
request; async research accepts `(plan, task)` and returns evidence; synchronous
decision accepts `(request, plan, evidence)` and returns D's assessment.
These callable boundaries are implemented; shared domain models are exported
from `app.models`. Research/URL/claim safety belongs to C and
decision/SMS formatting to D. This scaffold never fetches a supplied product URL.

The opt-in `/api/v1/mock/messages` simulator requires
`Settings(enable_mock_sms=True)`, an injected workflow, and D's `format_sms`
callable through `create_app`. Its local JSON is `{"event_id":"synthetic-1","text":"test"}`;
this is **not Photon JSON**. Mock sends remain in memory and include a simulation
label. Keep this developer API local: application-level authentication is not
implemented. Do not expose it publicly as a production service.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_api.py tests/test_photon.py tests/test_jobs.py -q
```

The full suite includes D's executable contracts and labeled synthetic fixtures,
B/C mocked HTTP tests, and A's injected API/job tests. No live provider claims follow
from these tests. Run `.venv/Scripts/python.exe -m pytest -q` (last run: 91 passed). Jobs/deduplication are bounded, single-process,
non-durable, and lost on restart. Default limits: 32 active jobs, 1,024 dedupe
records retained for one hour, two seller research calls, 20 seconds per evaluation
or job, and 16 KiB request bodies. Capacity exhaustion rejects new events; sends
that fail are recorded as failed without automatic retry. Status is internal only.
Long-running synchronous injected functions cannot be preempted by asyncio's
timeout; domain policy/formatters must stay short and provider I/O must be async.

See `docs/PACKET_A_HANDOFF.md` for observed checks and remaining integration gates.

## Photon Spectrum iMessage connection test

An independent TypeScript connection-test agent is in `app/adapters/spectrum`
(A-owned adapter path). Photon CLI 2.2.0 authenticated successfully; the VIZS Free
project and authorized test user are configured. Local credentials are in its
ignored `.env`. This uses iMessage through Spectrum SDK, not the disabled FastAPI
Photon webhook and not SMS. It currently echoes text; shopping workflow wiring
remains pending runtime/provider wiring; B/C/D implementations are merged. A real inbound iMessage and completed reply
request were observed; the user reported connection success. No provider delivery
receipt was inspected.

```powershell
cd app/adapters/spectrum
npm.cmd ci
npm.cmd run typecheck
npm.cmd start
```

The agent was started successfully in this session. After restarting the computer,
run the start command again. Do not run multiple copies for the same project.
Dependency installation reported 18 moderate advisories; no forced dependency
upgrade was applied. Treat this as a local hackathon prototype.

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
