# VIZS - online shopping assistant

**Project:** Evidence-backed online seller assessments through both Photon messaging and a Chrome extension with an animated on-page shopping pet. Both channels share one FastAPI/Grok/Tavily backend.
**Track recommendation:** VISA: Reimagine Shopping; **sponsored side-track candidate:** Photon 2.0 Messaging Agent. Humans finalize tracks.

## Status (checkpoint `62f1ac8`, Saturday Oct 17 2026)

| Area | State |
|---|---|
| Backend workflow | Implemented: Grok extraction, Tavily research, URL safety, deterministic risk policy, research status counts, labeled unverified links |
| Promise sheet | Implemented: bounded Tavily Extract of up to 3 seller pages, Grok promise extraction, Python quote-span validation, shipping/arrival/returns rows, `.com`/`.net` RDAP registration context; image checks always report unavailable |
| Extension backend boundary | Implemented: `POST /api/v1/extension/evaluate` with pairing token, origin allowlist and request budget |
| Chrome extension / pet UI | Implemented in `extension/` (MV3, user-triggered, offline-tested: 52 Node tests, real offline backend smoke, headless Chrome render check). Manual install check and live run pending |
| Photon iMessage | One registered-phone round trip confirmed by the user (Grok, Tavily 5 returned / 2 retained, VERIFY_FIRST, cited reply). Bounded test bridge, now started and stopped by `npm run shop` (PH-03, offline check passed on macOS). Live re-run pending |
| SMS, FastAPI Photon webhook, hosting | Not verified; `/webhooks/photon` is deliberately disabled |
| Tests | 642 Python, 79 extension and 38 Spectrum (bridge + launcher) tests pass, 0 xfail (macOS, Oct 17). QA verdict: ready with caveats (manual browser and live checks open); see `docs/QA_REPORT.md` |

**Immediate next steps:** save the mandatory Devpost draft (10:30 PM PDT tonight), load and manually check the extension (see `extension/README.md`), then one authorized live run per channel. See [next steps](docs/NEXT_STEPS.md).

## Run the local API

Python 3.11+ (tested with 3.12 on Windows and 3.14 on macOS).

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m app.workflow.dev_server            # offline, loopback, port 8000
```

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[test]'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m app.workflow.dev_server
```

`dev_server` binds to `127.0.0.1` and forces offline mode unless `--live` is passed. `--pair` creates `VIZS_EXTENSION_TOKEN` in the ignored root `.env` if absent (the value is never printed). `--port` selects 1024-65535. Running `uvicorn app.main:app` directly also works and uses `VIZS_PROVIDER_MODE` from `.env`.

Copy `.env.example` to `.env` only if you do not already have one:

```dotenv
VIZS_PROVIDER_MODE=offline
VIZS_ENABLE_MOCK_SMS=false
XAI_API_KEY=your_xai_key
XAI_MODEL=your_supported_model_id
# Optional: faster non-reasoning model for the promise reader (falls back to XAI_MODEL).
XAI_PROMISE_MODEL=
TAVILY_API_KEY=your_tavily_key
VIZS_GROK_TIMEOUT_SECONDS=30
VIZS_EVALUATION_TIMEOUT_SECONDS=100
VIZS_EXTENSION_TOKEN=
VIZS_EXTENSION_ORIGINS=
VIZS_EXTENSION_REQUESTS_PER_MINUTE=6
VIZS_EXTENSION_MAX_INFLIGHT=1
```

Keys alone never enable provider calls. `VIZS_PROVIDER_MODE=live` (or `dev_server --live`) allows requests to use paid credits; set it only when authorized. No provider call happens on startup. Environment variables take precedence over `.env`; loading does not modify the process environment.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | No external calls; reports assembly readiness and provider mode, not provider access |
| `POST /api/v1/evaluate` | Local developer evaluation; body `{request_id, message_text, channel: "debug"}`; returns the `Assessment`. Requires `Content-Type: application/json` (else 415); any request with an `Origin` header gets 403 (not for browsers) |
| `POST /api/v1/evaluate-message` | Loopback bridge used by the Spectrum test bridge; returns `{assessment, message_text}`. Same JSON-only / no-`Origin` rule as `/evaluate` |
| `POST /api/v1/extension/evaluate` | Extension route: same body and response as `evaluate-message`, plus pairing, Origin allowlist and budget checks (below); also requires `application/json` (415) |
| `POST /api/v1/mock/messages` | Opt-in simulator (`VIZS_ENABLE_MOCK_SMS=true`); body `{"event_id","text"}`; **not Photon JSON**, output labeled `MOCK SIMULATION`. 404 when disabled; when enabled, the same JSON-only / no-`Origin` rule as `/evaluate` (403, 413 for a declared oversized body, 415), checked before the body is read |
| `POST /webhooks/photon` | Always 503; no Photon callback, auth or ACK contract is assumed |

Offline request (macOS):

```sh
curl -s http://127.0.0.1:8000/api/v1/evaluate -H 'Content-Type: application/json' \
  -d '{"request_id":"local-1","message_text":"Check https://example.com/product","channel":"debug"}'
```

PowerShell:

```powershell
$body = @{ request_id = 'local-1'; message_text = 'Check https://example.com/product'; channel = 'debug' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/evaluate -ContentType 'application/json' -Body $body
```

In offline mode a valid request returns a partial assessment explaining that extraction is unavailable and the check could not be completed (try again later); it does not ask again for a URL the user already sent. A missing URL returns a clarification asking for it. Declared bodies over the size cap get 413 before they are read.

### Extension access

`/api/v1/extension/evaluate` requires `Authorization: Bearer <VIZS_EXTENSION_TOKEN>` and rejects before any provider work:

- 503 if no token is configured, 401 for a missing or wrong token.
- 403 if an `Origin` header is present and not in `VIZS_EXTENSION_ORIGINS` (exact `chrome-extension://<32 a-p chars>` values; no wildcards). Requests without `Origin` still need the token. Add the unpacked extension's ID here once it exists.
- 429 above `VIZS_EXTENSION_REQUESTS_PER_MINUTE` (default 6) or `VIZS_EXTENSION_MAX_INFLIGHT` (default 1).
- The body must still use `channel: "debug"`; there is no `extension` channel in the contracts. Optional price travels inside `message_text`.

This is local pairing for a developer machine, not public authentication. The budget is per process and resets on restart. Do not expose this API publicly.

## Limits and behavior

Defaults: 32 active jobs, 1,024 dedupe records kept for one hour, two seller research calls, one Tavily Extract call (up to 3 seller pages, 15 s), 30 s per Grok extraction, 100 s per evaluation (hard cap 120 s), 16 KiB request bodies. Jobs and dedupe are in-process, non-durable and lost on restart. Capacity exhaustion rejects new events; failed sends are recorded without retry. Missing configuration, provider failures and timeouts stay explicit; search snippets stay unverified and never become verified facts. Long-running synchronous injected functions cannot be preempted by asyncio's timeout.

## Photon Spectrum iMessage

`app/adapters/spectrum` is an A-owned TypeScript adapter using the Spectrum SDK over iMessage. It is not SMS and not the FastAPI webhook. Credentials (`PROJECT_ID`, `PROJECT_SECRET`) and `VIZS_REGISTERED_RECIPIENT` live in its ignored `.env` (see its `.env.example`); process environment variables override it.

- `npm start` runs `src/index.ts`, which is still the original **echo** agent.
- `src/test-bridge.mjs` is the bounded shopping bridge used for the confirmed live test: registered recipient only, up to three inbound messages, at most one URL evaluation, ten-minute expiry, no send retries.
- `src/launch.mjs` (`npm run shop`) starts the loopback Python API (`app.workflow.dev_server`), waits for `/healthz`, runs the bridge, and stops both when either exits or on Ctrl+C. It holds a single-instance PID lock, refuses before starting anything when configuration is missing, and prints only presence and the bridge's privacy-safe status lines. `--live` (paid provider calls) is passed only when you add it. Python is `VIZS_PYTHON`, else the repo `.venv`, else `python3` / `py -3`. Details: [app/adapters/spectrum/README.md](app/adapters/spectrum/README.md).

macOS / Linux:

```sh
cd app/adapters/spectrum
npm ci
npm run typecheck
npm test                      # bridge + launcher unit tests
npm run shop:check            # offline: config presence, API start, /healthz, clean stop; no Spectrum
npm run shop                  # offline API + bounded iMessage bridge (sends real replies)
npm run shop -- --live        # authorized live run only: API may use Grok/Tavily credits
```

Windows (PowerShell):

```powershell
cd app/adapters/spectrum
npm.cmd ci
npm.cmd run typecheck
npm.cmd test
npm.cmd run shop:check
npm.cmd run shop -- --live    # authorized live run only
```

Default API port is 8787 (`-- --port N` or `VIZS_LAUNCH_PORT`). Exit codes: 0 bounded test finished, 1 failure, 2 missing configuration, 3 another launcher or port already in use, 130/143 interrupted. Installation reported 18 moderate dependency advisories; none were force-upgraded.

## Evidence policy

Unknown sellers are not automatically fraudulent and a low price does not prove counterfeit goods. `LOWER_RISK` does not verify authenticity; `HIGHER_RISK` is not a legal finding. No authenticity or fraud percentages. Merchant policy quotes show what the merchant wrote, not that it will perform. Domain registration date is context, not business age or fraud evidence. Fixtures and mocks are never presented as live sponsor usage.

## Documentation map

- Current work: [NEXT_STEPS](docs/NEXT_STEPS.md), [EXTENSION_SCOPE](docs/EXTENSION_SCOPE.md), [CREDIBILITY_CHECKING](docs/CREDIBILITY_CHECKING.md), [ACCEPTANCE_TESTS](docs/ACCEPTANCE_TESTS.md)
- Design: [PROJECT_BRIEF](docs/PROJECT_BRIEF.md), [ARCHITECTURE](docs/ARCHITECTURE.md), [API_CONTRACTS](docs/API_CONTRACTS.md)
- Coordination: [OWNERSHIP](docs/OWNERSHIP.md), [AGENT_HANDOFF](docs/AGENT_HANDOFF.md), [TECH_LEAD_PLAN](docs/TECH_LEAD_PLAN.md), `docs/skills/`
- Submission: [SPRINT_PLAN](docs/SPRINT_PLAN.md), [SUBMISSION_CHECKLIST](docs/SUBMISSION_CHECKLIST.md), [TRACK_DECISION](docs/TRACK_DECISION.md), [INTEGRATION_RUNBOOK](docs/INTEGRATION_RUNBOOK.md)
- Historical handoffs (records of earlier runs, not current status): PACKET_A_HANDOFF, PACKET_WORKTREE_HANDOFF, RUNTIME_HANDOFF, INBOUND_TEST_HANDOFF, RESEARCH_OUTPUT_HANDOFF, LIVE_KEYWORD_PROBE

Tool instruction files: `AGENTS.md` (shared source), `CLAUDE.md`, `.github/copilot-instructions.md`, `.cursor/rules/project.mdc`, plus Copilot agents/prompts/skills under `.github/`. `COPILOT_PLAN_TEXT.txt` is the original SMS-first planning prompt, kept for history.

## Sources consulted (documentation, not proof of credentials)

- Project brief and official DubHacks Hacker Guide supplied by the team, October 17, 2026.
- xAI: https://docs.x.ai/developers/tools/overview, https://docs.x.ai/developers/model-capabilities/text/structured-outputs
- Tavily: https://docs.tavily.com/documentation/api-reference/endpoint/search, https://docs.tavily.com/documentation/api-reference/endpoint/extract
- Verisign RDAP: https://www.verisign.com/news-insights/registration-data-access-protocol/help/
- Photon 2.0: https://photon.codes/blog/introducing-photon-2.0, Spectrum SDK: https://photon.codes/docs/spectrum-ts, public API spec: https://github.com/photon-hq/api
- VS Code agent customization: https://code.visualstudio.com/docs/agent-customization/custom-agents
