# Packet D: contracts, policy, QA

This is a shared, manually read task guide, not an automatically installed tool skill. Read root `AGENTS.md`, `docs/OWNERSHIP.md`, and `docs/API_CONTRACTS.md`. Own shared models, decision code, shared fixtures, and assigned QA tests per the ownership table.

## Work packets

1. 30 minutes first: define Pydantic request, orchestrator plan, source/evidence, assessment, and normalized transport models. Use bounded fields, forbidden extras, timezone-aware timestamps, and Decimal for money. These are internal contracts, never Photon wire fields. Share two labeled synthetic fixtures and coordinate the baseline with A.
2. 45–60 minutes: pure deterministic rules and concise SMS formatting. Agree rule triggers before implementation. Price/authorization uncertainty alone must not become fraud evidence.
3. 45–60 minutes: contract/policy/formatting tests and injected end-to-end tests; integrated QA after A/B/C are connected.

Dependencies: contracts start first; policy can use fixtures. Integrated QA needs A/B/C. Do not edit their implementation or owned tests without reassignment.

## Acceptance

- Missing listing yields `INSUFFICIENT_EVIDENCE / NEED_MORE_INFORMATION`; weak, missing, allegation-only, or contradictory evidence yields conservative `VERIFY_FIRST`.
- Lower-risk decisions need grounded relevant evidence; higher-risk decisions need defined substantial adverse findings. Neither means authenticity certainty. No numerical fraud probabilities.
- Every factual reason is linked to supporting retrieved evidence. Unknowns belong in missing information; do not invent citations.
- Formatter preserves policy and intact source links, states uncertainty, and clearly labels fixtures. Verify actual SMS encoding/segments separately.
- Tests cover false certainty from discounts, unknown authorization, adverse findings, contradictions, unsupported tasks, and source-free fallback.

Once available, run `python -m pytest tests/test_contracts.py tests/test_policy.py tests/test_sms.py tests/test_e2e.py -q`. A runs the full suite after integration. Passing offline QA does not prove Photon delivery, live Grok access, or seller authenticity.

Handoff frozen schema details, fixtures, policy truth table, commands/results, and integration requirements using `docs/AGENT_HANDOFF.md`.
