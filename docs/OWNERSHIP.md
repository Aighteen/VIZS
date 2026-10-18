# Development ownership

Status: coordination setup only. No human owners or AI sessions have been assigned. Application paths below are proposed until implementation exists. A person can hold multiple roles; each concurrent editing session still needs an isolated checkout.

## Assignments

The human coordinator fills this table before concurrent implementation. Record an actual base commit when contracts are frozen. A maintains the table afterward and communicates updates to all sessions.

| Packet | Human owner / AI tool + session | Branch | Worktree/checkout | Status |
|---|---|---|---|---|
| A: integration, Photon, submission coordination | TBD | `feat/packet-a-api-photon` | TBD | Unassigned |
| B: Grok extraction | TBD | `feat/packet-b-grok` | TBD | Unassigned |
| C: research and evidence | TBD | `feat/packet-c-research` | TBD | Unassigned |
| D: contracts, policy, QA | TBD | `feat/packet-d-policy-qa` | TBD | Unassigned |

- Integration/merge owner: TBD (A).
- Human Devpost submitter: TBD. Human backup: TBD.
- Contract base commit: TBD. Search provider: TBD (Tavily preferred).
- Photon account-specific contract: UNVERIFIED.

## Exclusive writable areas

| Owner | Paths |
|---|---|
| A | `app/main.py`, `app/config.py`, `app/api/`, `app/adapters/`, `app/workflow/`; dependency manifests/lockfiles, `.env.example`, `.gitignore`, deployment config; `tests/test_api.py`, `tests/test_photon.py`, `tests/test_jobs.py`; `README.md`, shared coordination and submission docs, tool entry files |
| B | `app/services/grok.py`, `app/agents/`; `tests/test_grok.py` |
| C | `app/research/`, `app/services/tavily.py`; `tests/test_research.py`, `tests/test_url_safety.py` |
| D | `app/models/`, `app/decision/`; `tests/conftest.py`, `tests/fixtures/`, `tests/test_contracts.py`, `tests/test_policy.py`, `tests/test_sms.py`, `tests/test_e2e.py`; `docs/API_CONTRACTS.md` |

A owns shared package initializers such as `app/__init__.py`, `app/services/__init__.py`, and `tests/__init__.py`. Each packet owns initializers within its exclusive directories. New files outside the table require assignment by the coordinator. Frontend work is deferred; if explicitly requested, A assigns exact frontend paths separately.

## Start and integration sequence

1. D defines the shared request, plan, evidence, assessment, and transport models from `API_CONTRACTS.md`, plus synthetic fixtures. A reviews and integrates the contract baseline. Do not treat the illustrative docs as frozen executable contracts.
2. A sets up the dependency manifest. B/C/D request dependency changes through A. Before the baseline is ready, B/C can inspect provider docs and design fixtures without duplicating models or editing shared files.
3. Start each implementation branch from the same reviewed contract baseline in separate worktrees or clones. Record the actual branch, checkout, and assignment above. This setup document does not create branches or worktrees.
4. A builds the fixture-backed API while B builds extraction, C builds research, and D builds policy/QA in parallel. Use typed injected fakes at unfinished boundaries.
5. Each owner reports tests and limitations using `AGENT_HANDOFF.md`. A integrates contracts/API, Grok, research, policy, then verified Photon delivery. D verifies the integrated flow.
6. Only the integration owner merges when instructed. No automatic push, deployment, paid probes, or submission.

If an assignment conflicts with this table, the coordinator records the reassignment and notifies affected sessions before concurrent edits. Worktree copies of this table are not a distributed lock.

## Submission protection (PDT)

Human submitter targets Saturday October 17, 2026 at 10:00 PM for the mandatory 10:30 PM draft, and Sunday October 18 at 9:15 AM for the 10:00 AM final. Freeze features Sunday 7:30 AM. Preserve at least 30 minutes for final upload checks. A coordinates; humans select tracks and submit. See `SPRINT_PLAN.md` and `SUBMISSION_CHECKLIST.md`.
