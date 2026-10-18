# Runtime wiring handoff

> Historical record of an earlier run; test counts, paths and statuses below are not current. See [NEXT_STEPS.md](NEXT_STEPS.md).

## Assignment and outcome

Packet A runtime wiring, in C:\Github\VIZS-packet-a on feat/packet-a-integration, starting at ecee580. User supplied configuration locally; values were never displayed or copied. Preserve unrelated untracked .vscode/. Changes remain local, uncommitted and unpushed.

## Changed paths

- app/config.py: root .env loading without process mutation, environment precedence, offline/live mode, mock simulator switch, hidden key reprs.
- app/main.py and app/workflow/runtime.py: lifespan-owned Grok client, shared models, Grok/Tavily/policy/formatter composition; injected workflows retained. Shutdown cancels jobs before client closes.
- app/workflow/service.py: propagate research status/uncertainty as missing information without weakening D policy.
- app/api/routes.py: health reports assembly readiness and provider mode; Photon remains disabled.
- tests/test_api.py and tests/test_photon.py: API tests use real contracts/adapters with mocked HTTP; offline and missing-key paths skip network; failure/timeout/malformed responses; snippets conservative; simulator deduplication/labeling; client close; dotenv precedence and repr privacy.
- pyproject.toml: python-dotenv runtime dependency. .env.example, README, docs/NEXT_STEPS.md, docs/INTEGRATION_RUNBOOK.md, docs/OWNERSHIP.md and docs/skills/packet-a.md updated for actual behavior.

## Checks and dependencies

Installed python-dotenv with `uv pip install --python C:\Github\VIZS\.venv\Scripts\python.exe "python-dotenv>=1.0,<2"` (1.2.4). Official python-dotenv documentation checked for dotenv_values semantics. No Grok/Tavily API requests or paid usage.

`& C:\Github\VIZS\.venv\Scripts\python.exe -m pytest -q`: 103 passed, one installed Starlette/httpx deprecation warning, exit 0. `git diff --check`: exit 0.

A temporary local uvicorn subprocess bound to loopback was exercised with provider mode forced offline, then terminated. GET /healthz => 200, evaluation_ready true, photon_enabled false, provider_mode offline. POST /api/v1/evaluate with placeholder listing => 200, INSUFFICIENT_EVIDENCE / NEED_MORE_INFORMATION, partial, explicit extraction-unavailable explanation. Presence-only inspection confirmed all three provider settings populated; it does not establish validity or account access.

## Next step and blockers

No further code wiring is needed to construct the local pipeline. Run from A's worktree using the existing venv or install the updated manifest into a fresh venv. Configuration stays offline by default even with keys. Live evaluations require explicit VIZS_PROVIDER_MODE=live and authorization for credit usage; perform small Grok/Tavily verification, inspect model/schema support and real returned records. Do not claim live access based on these tests. Photon callback/auth/send remains unverified/disabled. Search snippets remain unknown and do not establish authorization/authenticity. D policy currently excludes neutral snippets from assessment citations; richer evidence retention is a separate D/C handoff, not silently changed here. Jobs remain in-process and non-durable.
