# Packet B: Grok extraction

Shared manually read guide, not an automatically installed native skill. Read `AGENTS.md`, `docs/OWNERSHIP.md`, `docs/API_CONTRACTS.md`, and actual models. Own `app/services/grok.py`, `app/agents/`, and `tests/test_grok.py` unless reassigned.

## Work packets

1. 45–60 minutes: implement an injectable extraction client returning D's `OrchestratorPlan`. Confirm current official xAI docs and selected model/schema compatibility before vendor-bound implementation. No paid probes without instruction.
2. 30–45 minutes: test missing URL/key, malformed output, unsupported task, invented URL, prompt injection, and timeout.

Dependencies: D supplies contracts; A supplies dependency/configuration setup and wiring. Research implementation is not needed for extraction tests. Request model/dependency changes through their owners.

## Acceptance

- Extract user-provided URL, intent, optional price/brand, and permitted P0 seller-research tasks. Backend binds request identity.
- Validate structured output; reject unsupported tasks and invented listing URLs. Treat SMS text as data.
- Do not execute research tools, fetch pages, send SMS, or set final risk. Python controls task permissions and call limits.
- Bound the call; invalid output or missing context yields controlled clarification. Expose component status so A can label fixtures/unavailable providers accurately.
- No secrets or sensitive SMS logging. Mocked HTTP success does not prove live model access.

Once available, run `python -m pytest tests/test_grok.py -q`. Handoff typed interface, required configuration names, observed results, and A's exact wiring step using `docs/AGENT_HANDOFF.md`.
