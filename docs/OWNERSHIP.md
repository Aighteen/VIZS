# Development ownership

Status: Packet A scaffold implemented locally; D executable contracts and B/C/D implementations remain absent. Packet A was assigned to this Codex session by the human. Packets B-D assigned by the human to dedicated Codex agents; human identities remain unspecified. One person may hold multiple roles, but concurrent editing sessions need separate checkouts.

## Assignment register

The human coordinator assigns each session; A maintains this register afterward. Communicate assignments to every active session because worktree copies are not shared locks.

| Packet | Human / AI tool and session | Branch | Checkout/worktree | Status |
|---|---|---|---|---|
| A: integration, Photon, submission coordination | Human name TBD / current Codex session | `feat/packet-a-integration` | `C:\Github\VIZS-packet-a` | Integration coordinator; preserved local scaffold |
| B: Grok extraction | Codex Packet B agent | `feat/packet-b-grok` | `C:\Github\VIZS-packet-b` | Assigned; contracts first |
| C: research and evidence | Codex Packet C agent | `feat/packet-c-research` | `C:\Github\VIZS-packet-c` | Assigned; contracts first |
| D: contracts, policy, QA | Codex Packet D agent | `feat/packet-d-policy-qa` | `C:\Github\VIZS-packet-d` | Assigned; establish Contract gate first |

- Integration owner: current Packet A Codex session; merges require explicit instruction.
- Human Devpost submitter and backup: TBD.
- Inspected repository base commit: `ffc3e85`; D executable contract baseline remains unavailable.
- Research provider: TBD (Tavily preferred).
- Photon Spectrum: Free VIZS project configured, authorized iPhone registered, SDK iMessage echo agent running. Inbound text and completed reply request observed; user reported connection success. FastAPI callback/auth/send contract remains UNVERIFIED; no webhook enabled.

## Exclusive writable paths

| Owner | Paths |
|---|---|
| A | `app/main.py`, `app/config.py`, `app/api/`, `app/adapters/`, `app/workflow/`; dependency manifests/lockfiles, `.env.example`, `.gitignore`, deployment configuration; `tests/test_api.py`, `tests/test_photon.py`, `tests/test_jobs.py`; `README.md`, shared coordination/submission docs, tool instruction entry files |
| B | `app/services/grok.py`, `app/agents/`, `tests/test_grok.py` |
| C | `app/research/`, `app/services/tavily.py`, `tests/test_research.py`, `tests/test_url_safety.py` |
| D | `app/models/`, `app/decision/`, `tests/conftest.py`, `tests/fixtures/`, `tests/test_contracts.py`, `tests/test_policy.py`, `tests/test_sms.py`, `tests/test_e2e.py`, `docs/API_CONTRACTS.md` |

A owns shared package initializers (`app/__init__.py`, `app/services/__init__.py`, `tests/__init__.py`). Each packet owns initializers within its exclusive directories. New areas, including any frontend, need an explicit owner/path assignment. Request dependency changes through A and model/shared fixture changes through D.

## Dependencies and integration

1. D defines shared Pydantic contracts and labeled synthetic examples from `API_CONTRACTS.md`; A reviews and integrates a baseline. Illustrative docs are not frozen executable contracts.
2. A establishes dependency/setup configuration. Before the baseline exists, B/C can inspect docs and design their adapters without duplicating shared models.
3. Create each implementation branch from the same reviewed base in separate worktrees or clones. Record actual checkout/branch names above. This document does not create them.
4. A builds the fixture-backed API while B builds extraction, C builds research, and D builds policy/QA. Use injected typed fakes at unfinished boundaries.
5. Owners provide `AGENT_HANDOFF.md` reports. A integrates contracts/API, Grok, research, policy, then verified Photon transport. D checks the full flow.
6. Only A merges when instructed. No automatic push, deployment, paid probes, or submission. Do not reset or delete tracked/untracked changes to make status clean; preserve and report unexpected changes.

These are development roles. Current runtime scope is one central Grok orchestrator, backend-controlled research tools, deterministic Python decisions, and one FastAPI service. A central AI prompting specialist runtime AI agents is a separate scope decision, not implied by four development packets.

## Submission protection (PDT)

Human submitter targets Saturday October 17, 2026 at 10:00 PM for the mandatory 10:30 PM draft, and Sunday October 18 at 9:15 AM for the 10:00 AM final. Feature freeze: Sunday 7:30 AM. Preserve at least 30 minutes for upload checks. Humans select tracks and submit; see `SPRINT_PLAN.md` and `SUBMISSION_CHECKLIST.md`.

