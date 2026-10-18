# Packet D: contracts, policy, QA

Shared manually read guide, not an automatically installed native skill. Read `AGENTS.md`, `docs/OWNERSHIP.md`, and `docs/API_CONTRACTS.md`. Own shared models, decision code, shared fixtures, and assigned QA tests.

## Work packets

1. 30 minutes first: define Pydantic request, plan, source/evidence, assessment, and normalized transport contracts. Bound fields, forbid extras, use timezone-aware timestamps and Decimal for money. Internal transport fields are not Photon wire fields. Share labeled synthetic positive/insufficient examples and coordinate the baseline with A.
2. 45–60 minutes: pure deterministic rules and concise SMS formatting; agree triggers before implementation.
3. 45–60 minutes: contract/policy/formatting and injected end-to-end tests; integrated QA once A/B/C are wired.

Dependencies: contracts start first; policy uses fixtures. Integrated QA needs A/B/C. Do not edit their implementation or owned tests without reassignment.

## Acceptance

- Missing listing yields `INSUFFICIENT_EVIDENCE / NEED_MORE_INFORMATION`. Weak, absent, allegation-only, or contradictory evidence yields conservative `VERIFY_FIRST`.
- Lower-risk conclusions require grounded relevant support; higher-risk conclusions require defined substantial adverse findings. Unknown authorization and discounts are not fraud proof. No authenticity certainty or numerical fraud probability.
- Factual reasons link to supporting retrieved evidence. Unknowns belong in missing information, not invented source records.
- Formatter preserves policy, uncertainty, intact citations, and fixture labels. Actual SMS segment/encoding behavior needs separate verification.
- Tests cover official support, adverse findings, unknown authorization, discounts, allegations, contradictions, and source-free fallback.

Once available, run `python -m pytest tests/test_contracts.py tests/test_policy.py tests/test_sms.py tests/test_e2e.py -q`. A runs the integrated full suite. Offline QA does not prove real SMS delivery, model access, or authenticity.

Handoff frozen schema details, fixtures, policy truth table, commands/results, and integration requirements using `docs/AGENT_HANDOFF.md`.
