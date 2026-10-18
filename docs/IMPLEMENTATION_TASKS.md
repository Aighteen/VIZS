# Parallel implementation tasks — ownership and acceptance criteria

Assign **up to four students**. Team size and identities are currently unknown; one person may own several packets. Do not assume a structure already exists; adapt paths to repo.

## Contract gate (everyone; first 20–30 minutes)

- [ ] Human integration owner chooses one shared `Assessment`, `Evidence`, `OrchestratorPlan` contract from `docs/API_CONTRACTS.md`.
- [ ] Prove Grok key/model access, search provider key, and Photon 2.0 beta API/channel independently; record blockers accurately.
- [ ] Agree on a JSON fixture for **one** happy path and **one** insufficient-evidence path.
- [ ] Confirm final repo layout with `git status`; avoid overlapping edits.

## Packet A — API + Photon adapter (integration owner)

**Suggested paths:** `app/main.py`, `app/api/routes.py`, `app/adapters/photon.py`, `tests/test_api.py`, deployment config.

1. Implement `GET /healthz`, `POST /api/v1/evaluate`; for webhook implement a stub accepting only **verified** real Photon 2.0 contract once available.
2. Mock adapter must be independently testable and plainly not a live Photon event.
3. Verify inbound auth using documented provider-specific method; dedupe by documented event/message ID; send an actual SMS through Photon.
4. Avoid running full Grok research inside slow webhook response; bounded asynchronous mechanism after appropriate validation.

**Done:** local POST gets an `Assessment`; real inbound sends one live reply exactly once, or missing access is explicitly marked blocked.

## Packet B — Grok orchestration (LLM owner)

**Suggested paths:** `app/services/grok.py`, `app/models/orchestrator.py`, `tests/test_grok.py`.

1. Convert SMS to URL/intent/tasks and validate structured output.
2. Restrict allowed tasks; cap tool invocation; no arbitrary tool execution or open internet SSRF based on model arguments.
3. Handle no-URL, malformed model output, API timeout, and unavailable key.

**Done:** returns typed plan and predictable fallback; live Grok integration separately exercised if key works.

## Packet C — research + evidence (research owner)

**Suggested paths:** `app/research/provider.py`, `app/research/evidence.py`, `tests/test_research.py`.

1. Choose Tavily OR Grok native web search. Implement a normalized provider interface returning URLs, title, excerpt and retrieval time.
2. Validate claims against returned source records; label allegations and unknowns; enforce URL safety and research call bounds.
3. Add fixtures for empty results and contradictory evidence.

**Done:** output always cites actually returned records or reports `INSUFFICIENT_EVIDENCE`.

## Packet D — decision + QA + demo (policy owner)

**Suggested paths:** `app/decision/rules.py`, `app/models/assessment.py`, `tests/test_policy.py`, demo script.

1. Pure deterministic mapping from evidence findings to assessment; no Grok-supplied arbitrary fraud score.
2. Cover no evidence, official seller authorization, multiple well-supported adverse findings, allegation-only evidence and inconsistent sources.
3. Test message length and source links; coordinate with Packet A for true SMS round trip and recording.

**Done:** pytest executes; policy does not promote allegation into fact or recommend solely due to discounts.

## Integration order (single owner controls shared files)

1. Merge model contract and local `/api/v1/evaluate` dummy fixture route.
2. Replace dummy with real Grok plan, then real search, then deterministic assessment.
3. Run tests and call local endpoint with real external service keys (secrets never logged).
4. Connect Photon adapter; send a real incoming SMS, verify real outbound, dedupe, timeout.
5. Freeze P0; add P1 **only if remaining time and reliability allow**.

## P1 packets (skip if any P0 gate fails)

- **Price:** compare exact same concentration, volume, condition, edition; annotate source+timestamp+merchant.
- **Card rewards:** manually configured **card labels only**; base rate, category/MCC uncertainty, activated-offer conditions, caps, and `Decimal` calculations; no banking secrets.
- **DETAILS:** fetch from stored assessment only if enough state; otherwise clearly state limitations.
