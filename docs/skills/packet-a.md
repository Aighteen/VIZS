# Packet A: API, workflow, Photon

Shared manually read guide, not an automatically installed native skill. Read `AGENTS.md`, `docs/OWNERSHIP.md`, `docs/API_CONTRACTS.md`, and `docs/INTEGRATION_RUNBOOK.md`. Follow the assigned writable paths.

## Work packets

1. 30â€“45 minutes: establish dependency manifest, configuration, app factory, `/healthz`, and `/api/v1/evaluate` using D's contracts and injected fixtures.
2. 45â€“60 minutes: wire the shared bounded workflow, separate mock transport, atomic in-process deduplication, and background jobs. Keep mock events separate from the real Photon endpoint.
3. 60â€“90 minutes: implement the Photon adapter only against verified account-specific callback/auth/send docs. Otherwise keep live transport disabled and document the blocker.

Dependencies: D supplies shared models first; B/C/D implementations replace typed fakes later. Do not duplicate extraction, research, or policy inside routes.

Current implementation: A-D are merged; shared contracts are in `app.models`.
Runtime wiring is now implemented locally; offline evaluations return partial
assessments and explicit clarification. Live mode requires explicit configuration. The combined offline suite passed 91 tests. See `docs/NEXT_STEPS.md`
for the next A assignment; older packet handoffs describe historical results.
The independent mock event is not a Photon wire contract.

## Acceptance

- Health needs no external calls; debug and SMS paths use the same evaluation workflow.
- Validate/authenticate callbacks and deduplicate before scheduling. ACK/retry behavior must follow actual Photon docs.
- Concurrent duplicate verified events schedule one job in the running prototype. Document restart/multi-worker limitations; no durable exactly-once claim.
- Bound jobs/calls and handle send failures explicitly. Do not blindly retry ambiguous outbound sends without documented idempotency support.
- Offline API/transport/job tests pass with labeled fakes. Actual inbound and handset reply are a separate authorized live gate.

Once manifest/tests exist, run `python -m pytest tests/test_api.py tests/test_photon.py tests/test_jobs.py -q` in the project environment. This is a proposed command, not a recorded result.

Handoff using `docs/AGENT_HANDOFF.md`. A coordinates merges/deadlines; humans submit. Frontend work requires explicit assignment and must not delay the SMS flow.
