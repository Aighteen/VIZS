# VIZS - fragrance shopping assistant

**Project:** Evidence-backed fragrance seller assessments through both Photon messaging and a Chrome extension with an animated on-page shopping pet.
**Track recommendation:** VISA: Reimagine Shopping; **sponsored side-track candidate:** Photon 2.0 Messaging Agent.
**Status:** Packets A-D merged on `feat/packet-a-integration`; 116 offline tests pass. Runtime wiring is implemented locally; default offline mode makes no provider calls. A registered-phone iMessage test completed through Grok and Tavily; the user confirmed receipt of the reply with unverified source links.
**Current phase:** Extension scope approved; frontend not implemented. Existing backend and cited iMessage round trip tested. See [next steps](docs/NEXT_STEPS.md).
**Immediate next step:** Assign the extension owner and build the pet shell/result panel against offline fixtures; A defines safe backend access. See [extension scope](docs/EXTENSION_SCOPE.md). Paid API calls still require instruction. Humans finalize tracks.

## Run the local API

Use Python 3.11+ (tested with 3.12):

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[test]'
.venv/Scripts/python.exe -m uvicorn app.main:app
```

`GET /healthz` performs no external calls and reports assembly readiness plus provider mode; it does not prove provider access. `POST /api/v1/evaluate` now uses the assembled workflow. In default offline mode, a valid request returns a partial assessment explaining unavailable extraction; missing input returns clarification.
`POST /webhooks/photon` returns a local disabled 503; no vendor acknowledgement,
authentication, or retry behavior is assumed.

`create_app()` loads the root `.env` without changing process environment; environment
variables take precedence. Existing injected workflows remain supported for tests.
Copy `.env.example` to `.env` only if you do not already have a local `.env`.

```dotenv
VIZS_PROVIDER_MODE=offline
VIZS_ENABLE_MOCK_SMS=false
XAI_API_KEY=your_xai_key
XAI_MODEL=your_supported_model_id
TAVILY_API_KEY=your_tavily_key
```

Keys alone never enable provider calls. Explicit `VIZS_PROVIDER_MODE=live` allows
requests to use credits; set it only when authorized. No provider call happens on
startup. Grok's client closes on shutdown after jobs stop. Missing configuration,
provider failures and timeouts stay explicit; research snippets remain unverified.
Photon's webhook remains disabled regardless of provider mode.

Try an offline request while the local server is running:

```powershell
$body = @{ request_id = 'local-1'; message_text = 'Check https://example.com/perfume'; channel = 'debug' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/evaluate -ContentType 'application/json' -Body $body
```

The opt-in `/api/v1/mock/messages` simulator requires
`VIZS_ENABLE_MOCK_SMS=true` (or `Settings(enable_mock_sms=True)`). The assembled
workflow and D's formatter are supplied automatically; custom injected workflows
must provide their own formatter. Its local JSON is `{"event_id":"synthetic-1","text":"test"}`;
this is **not Photon JSON**. Mock sends remain in memory and include a simulation
label. Keep this developer API local: application-level authentication is not
implemented. Do not expose it publicly as a production service.

```powershell
.venv/Scripts/python.exe -m pytest tests/test_api.py tests/test_photon.py tests/test_jobs.py -q
```

The full suite includes D's executable contracts and labeled synthetic fixtures,
B/C mocked HTTP tests, and A's injected API/job tests. No live provider claims follow
from these tests. Run `.venv/Scripts/python.exe -m pytest -q` (last run: 116 passed). Jobs/deduplication are bounded, single-process,
non-durable, and lost on restart. Default limits: 32 active jobs, 1,024 dedupe
records retained for one hour, two seller research calls, 30 seconds per Grok extraction and 55 seconds per evaluation
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

## Start now â€” two ways to get a Copilot implementation plan

**Universal (works regardless of harness):** In VS Code Copilot Chat, select **Plan** if available, or `tech-lead`, and paste all text from `COPILOT_PLAN_TEXT.txt`. Ask for a file-by-file plan **without editing source**.

**Reusable command:**
- VS Code **Local harness**: run `/dubhacks-plan` from `.github/prompts/dubhacks-plan.prompt.md` (prompt files are Local-harness-only in the current VS Code docs).
- VS Code **Copilot harness**: run `/dubhacks-planning` from `.github/skills/dubhacks-planning/SKILL.md`, or invoke the `tech-lead` custom agent.
- **Codex**: open the repo, ensure root `AGENTS.md` is visible, then paste the request from `COPILOT_PLAN_TEXT.txt`. `AGENTS.md` is recognized by Codex; Copilot `.agent.md` files are **not** automatically equivalent to Codex's role system.

Read `docs/INTEGRATION_RUNBOOK.md` for integration blockers and the order to verify services.

## Current product MVP

User activates the Chrome extension on a fragrance listing -> clicks the animated pet -> FastAPI/Grok/Tavily research -> deterministic seller assessment -> pet result panel with labeled source links and uncertainty. Show Searching while the request is pending; later phases require real backend signals. See `docs/EXTENSION_SCOPE.md` for acceptance criteria. The extension itself has not been built.

Photon messaging and the extension are both core channels; the tested iMessage path is retained. SMS transport, public hosting and an always-on service remain unverified. Existing API setup below supports backend development, not an installed extension.

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


## Research response status

Relevant returned snippets now survive as unknown `search_snippet` references, with up to two intact links labeled "Unverified source". An authorization claim in a snippet does not change risk. The response distinguishes empty, filtered, unavailable and timed-out research and retains explicit authorization/authenticity uncertainty. Assessment research reports include bounded returned/retained/filtered counts without logging private message text. See `docs/RESEARCH_OUTPUT_HANDOFF.md`. The bounded phone listener is not always running; another live test requires explicitly starting it.


## Confirmed live checkpoint and next work

One registered-phone iMessage test completed: valid Grok extraction, Tavily returned five records with two retained/three filtered, VERIFY_FIRST / partial, and the user confirmed receipt of unverified source links. This does not verify authenticity, independently validate search snippets, establish SMS transport, or deploy a persistent service. Earlier handoffs describe historical runs.

The bounded bridge is `app/adapters/spectrum/src/test-bridge.mjs` (the default `npm start` remains the original echo agent). It requires Photon project credentials, `VIZS_REGISTERED_RECIPIENT` obtained from the project's opted-in registered user, and `VIZS_LOCAL_API=http://127.0.0.1:<port>/api/v1/evaluate-message`. Run the Python API on loopback with explicitly authorized live mode; run only one listener per project. Recipient/project credentials are supplied through process environment, never source code. The original live test used a temporary hidden supervisor that stopped both processes after the bounded evaluation; that local supervisor is not part of the repository. A reusable launch/stop command is the next operational improvement.

Next: build the user-triggered extension/pet shell and safe backend boundary, improve manufacturer/seller/brand/region source validation, then validate a live extension demo. A reproducible Photon launch/stop flow is also part of P0. Continue using conservative unknown outcomes; do not promote snippets to verified facts for a favorable demo.


## Credibility direction: merchant promises and evidence

The user-supplied Kept brief guides the next credibility-checking iteration: compare merchant promises with cited evidence for shipping, arrival and return terms, with careful domain-registration and image-reuse context. See [credibility specification](docs/CREDIBILITY_CHECKING.md). This is planned work; the current code still returns conservative seller assessments with unverified source links. Both Photon and the pet extension remain core. Payments, tracking, dispute filing and custom model training are not part of this change.
