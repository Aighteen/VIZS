# Packet B: Grok extraction

This is a shared, manually read task guide, not an automatically installed tool skill. Read root `AGENTS.md`, `docs/OWNERSHIP.md`, `docs/API_CONTRACTS.md`, and actual models. Own only `app/services/grok.py`, `app/agents/`, and `tests/test_grok.py` unless explicitly reassigned.

## Work packets

1. 45–60 minutes: build an injectable extraction client returning D's `OrchestratorPlan`. Confirm current official xAI docs and selected model/schema compatibility before implementing vendor calls. No paid probes without instruction.
2. 30–45 minutes: add malformed output, missing URL/key, unsupported task, hallucinated URL, prompt injection, and timeout tests.

Dependencies: D supplies shared models; A supplies dependency manifest/configuration and wires the client. C is not needed to test extraction. Request shared-model/dependency changes instead of editing those files.

## Acceptance

- Extract only user-provided product URL, intent, optional price/brand, and permitted P0 seller-research tasks. Bind request identity in the backend.
- Schema-validate output; reject unsupported tasks and invented URLs. Treat SMS text as untrusted data. Do not execute tools, fetch merchant pages, send SMS, or set final risk.
- Use a bounded call with controlled failure. Missing context or invalid output leads to clarification, never fabricated research. Expose enough status for A to label mocked or unavailable components.
- No API key, raw phone number, or sensitive SMS logging. Live key/model access remains unverified until an authorized probe actually passes.

Once available, run `python -m pytest tests/test_grok.py -q`. Use mocked HTTP/client responses for offline tests; they do not prove real model availability.

Handoff the typed interface, configuration names, results, and exact A wiring step using `docs/AGENT_HANDOFF.md`.
