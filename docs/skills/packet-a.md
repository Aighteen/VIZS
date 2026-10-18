# Packet A: API, workflow, Photon

This is a shared, manually read task guide, not an automatically installed tool skill. Read root `AGENTS.md`, `docs/OWNERSHIP.md`, `docs/API_CONTRACTS.md`, and `docs/INTEGRATION_RUNBOOK.md`. Writable paths are defined by the session assignment and ownership table.

## Work packets

1. 30–45 minutes: establish dependency manifest, configuration, app factory, `/healthz`, and local `/api/v1/evaluate` using D's contracts and injected fixtures.
2. 45–60 minutes: wire a shared bounded workflow, separate mock transport, atomic in-process deduplication, and background job handling. Keep mock events separate from the Photon endpoint.
3. 60–90 minutes: implement `app/adapters/photon.py` only against verified account docs. Isolate callback verification, normalization, sending, and provider result mapping. If docs/access are missing, keep real transport disabled and document the blocker.

Dependencies: D's frozen models first; B/C/D implementations replace injected fakes later. Do not implement competing extraction, research, or policy inside routes.

## Acceptance

- Health works without external APIs; debug requests return a typed assessment using the same evaluation workflow as SMS.
- Invalid callbacks are rejected before scheduling. ACK/status behavior follows verified Photon retry rules, not invented headers or payloads.
- Repeated verified events schedule one job in the running prototype; test concurrent duplicates. Jobs and dedupe are non-durable; document restart and multi-worker limitations.
- Provider deadlines and send failures yield explicit states; never blindly retry an ambiguous send without documented idempotency support.
- Tests in `tests/test_api.py`, `tests/test_photon.py`, and `tests/test_jobs.py` pass using labeled fakes. Real inbound and handset reply are a separate, authorized live gate.

Once the manifest and tests exist, run `python -m pytest tests/test_api.py tests/test_photon.py tests/test_jobs.py -q` in the project environment. Record the actual command/output; currently proposed commands are not test results.

Handoff using `docs/AGENT_HANDOFF.md`. A owns integration and deadline coordination; humans submit and select tracks. Optional browser UI must not delay the SMS flow.
