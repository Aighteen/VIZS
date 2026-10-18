# Architecture — staged MVP

## Purpose and minimum viable design

One Python FastAPI service and one orchestrating Grok call, with backend-owned tools and deterministic policy. Calling three research functions is **not** equivalent to needing three separately hosted agents.

```
[User SMS] -> [Photon 2.0 verified inbound adapter] -> [FastAPI event handler]
                                                   |
                                      [job / in-process task*]
                                                   v
                        [Grok classify into validated Intent + tasks]
                                                   v
                   [Backend allowed search provider: Tavily OR Grok web]
                                                   v
                  [Normalize Evidence: real URL, quote/claim, type, time]
                                                   v
               [Python policy: risk and action, no arbitrary probability]
                                                   v
                  [SMS formatter] -> [Photon outbound adapter] -> [User]

Developer pathway: POST /api/v1/evaluate -> same orchestrate/research/policy modules
```

`*` For very short MVP processing, a FastAPI `BackgroundTasks`-style job can keep webhook acknowledgement fast, **but does not survive process restarts**. If losing jobs is unacceptable, use a real queue or durable state. Do not pretend the in-process prototype is production reliable.

## Candidate module boundaries — adjust to actual repo

| Module | Scope | Must not own |
|---|---|---|
| `app/adapters/photon.py` | Verified Photon 2.0 event parse, auth, dedupe key extraction, outbound API | LLM prompt logic, seller risk policy |
| `app/api/routes.py` | `/healthz`, `/api/v1/evaluate`, `/webhooks/photon` | Provider details outside adapters |
| `app/services/grok.py` | Parse SMS intent; ask for permitted research tasks; optional response phrasing | Sending SMS, executing arbitrary tools, setting final risk |
| `app/research/provider.py` | Search-provider protocol, retries, latency guards | Purchase decision |
| `app/research/evidence.py` | Normalize source records, claim classifications, contradictions | Claim certainty outside evidence |
| `app/decision/rules.py` | Pure Python risk and purchase decision functions | HTTP calls, AI-created reward arithmetic |
| `app/models/*.py` | Typed Pydantic domain contracts | Vendor-private model fields |
| `app/workflow/service.py` | Order the calls and create bounded responses | Direct knowledge of Photon wire schema |

## Anti-hallucination and seller-risk policy

1. Never assert manufacturer authorization without manufacturer/directory evidence.
2. A missing authorization listing is an **unknown**, not a verified negative.
3. Reviews and complaint posts are allegations, not established fraud.
4. Discount alone does not establish counterfeit, including gray-market goods.
5. Every material factual sentence must trace to a **real retrieved source record**, with retrieval provenance and claim type; missing sources require a constrained answer.
6. If evidence is contradictory/weak: `INSUFFICIENT_EVIDENCE`, usually `VERIFY_FIRST` (or `NEED_MORE_INFORMATION` when basic product context missing).
7. `HIGHER_RISK` should require substantial **grounded** adverse signals; define triggers/tests with team review rather than invented score/probability.
8. `LOWER_RISK` means lower risk under observed criteria, not authenticity verified. No recommendation to buy solely for cheap price or card perks.

## Threat model and controls

- **Prompt injection:** adversarial instructions inside merchant pages are untrusted; no authority to change tools/policy/system prompt.
- **SSRF:** URLs can resolve to internal hosts or redirect internally; do not direct-fetch arbitrary target URLs without scheme/host/DNS/redirect checks. Prefer provider retrieval; validate user input separately.
- **Replay/duplication:** identify and deduplicate Photon message IDs per *verified* contract; short-lived memory is a demo tradeoff, not persistent guarantee.
- **SMS privacy:** redact phone numbers in logs, do not request full payment credentials, and avoid disclosure of personal card data.
- **Rate/cost bounds:** cap research tool calls, output length, retries and timeout; avoid infinite Grok tool-call loops.
- **Demo integrity:** `mock` flag and visible disclaimer when using mock providers; record the last confirmed live SMS round trip.

## Decision records to make immediately

- Photon inbound event fields/auth: **UNVERIFIED** until beta docs/account tested.
- Grok structured output + model: supported in current xAI docs for appropriate models, but team key/model availability **UNVERIFIED**.
- Search: Tavily (explicit URL records) preferred if key available; otherwise Grok native web search if citations are accessible in actual response format.
- Persistence: in-memory for demo only; upgrade only for repeat messages and restart resilience if needed.
- Hosting: any provider giving Python FastAPI public HTTPS and compatible background execution; deployment not assumed complete.
