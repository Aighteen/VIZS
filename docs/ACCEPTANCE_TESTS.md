# Completed-product acceptance test cases

Scope: online-seller promise/evidence assessment through both Photon iMessage and a Chrome animated-pet extension. This is the reference release checklist, not a claim every case has passed. Historical baseline: f5af5ba, 116 Python and four bridge tests. Each implementation handoff must link automated cases or label manual/live cases pending. Payments, certified timestamps, model training, disputes, purchase history and public store scores are excluded.

## Test conditions

Use labeled synthetic fixtures and mocked provider HTTP for automated tests. Never treat fixtures as sponsor usage. Live tests need explicit credit/message authorization; browser-store publication/deployment requires instruction. Public source URLs, quoted source text, retrieval times, provenance and unknowns must be retained; phone numbers and credentials must not enter logs or artifacts. A merchant statement is not verified fulfillment.

| ID | Case / setup | Expected result | Verification target |
|---|---|---|---|
| INPUT-01 | Valid product listing, optional explicit currency price | Backend-bound request identity; correct supplied URL/price; one seller task | Automated |
| INPUT-02 | Missing URL or multiple ambiguous URLs | Specific clarification, no invented listing or research | Automated |
| INPUT-03 | Model invents URL, unsupported task or price | Reject output, conservative response, no arbitrary tools | Automated |
| INPUT-04 | Invalid JSON, key missing, refusal, timeout | Controlled status; no raw provider body/secret | Automated |
| PROM-01 | Listing says free returns; same-region policy says customer pays | Cited conditional conflict with both real source quotes; no invented price/scam claim | Automated |
| PROM-02 | Merchant shipping estimate includes processing and transit | Preserve distinct ranges, business/calendar wording, region/conditions; no guaranteed arrival | Automated |
| PROM-03 | Local business address but no warehouse origin disclosure | Shipment origin unknown; do not infer local shipping | Automated |
| PROM-04 | Inspected policy omits a topic | Not disclosed in inspected source, never whole-site absence | Automated |
| PROM-05 | Policy retrieval unavailable or failed | Unavailable, distinct from not_disclosed; do not infer adverse conduct | Automated |
| PROM-06 | Model quote not a span of returned source | Reject quote/record; no invented evidence | Automated |
| PROM-07 | Unrelated seller, different region, conflicting terms (stale terms deferred for the hackathon) | Exclude unrelated evidence; qualify conflicts instead of merging conditions. Stale-terms detection is deferred: `retrieved_at` is retrieval time and no staleness model exists | Automated (stale: deferred) |
| PROM-08 | Merchant self-asserts authorization | Statement only; no manufacturer corroboration/authenticity claim | Automated |
| PROM-09 | Prompt injection in policy text | Treat as data; no tool/policy override; safe rendering | Automated |
| PROM-10 | Duplicated snippets / missing quote/time/URL | Deduplicate or reject; preserve honest provenance | Automated |
| RES-01 | Five results, only two valid and relevant | Received=5, retained=2, filtered=3; honest partial status | Automated |
| RES-02 | Empty provider response vs all sources rejected | Distinct empty/filtered statuses and useful explanation | Automated |
| RES-03 | HTTP error/timeout/missing provider key | Distinct unavailable/timeout; no unintended DNS/network for missing configuration | Automated |
| RES-04 | Search snippet vs extracted policy content | Keep content_kind; snippet does not become verified page policy | Automated |
| RES-05 | Provider-only policy extraction | Fixed API endpoint; public URL guards, bounded URLs/response/time/retries | Automated |
| RES-06 | Private IPv4/IPv6, mixed DNS, credential URL, redirect | Reject unsafe user/source targets; no unguarded direct fetching | Automated |
| DOM-01 | Registration date returned | Dated source/context; domain registration is not business age or fraud proof | Automated |
| DOM-02 | Unsupported domain, missing/future/invalid registration or timeout | Unknown/unavailable; no invented date or widened endpoint | Automated |
| IMG-01 | No live image provider/detector available | Explicit unavailable/unsupported status; no invented matches or AI-photo confidence | Automated |
| IMG-02 | Future image-match implementation with fixture | Similarity is context, not proof of identical goods or supplier | Deferred / explicit fixture only |
| RISK-01 | Unknown seller, young domain, discount or allegations alone | VERIFY_FIRST / INSUFFICIENT_EVIDENCE; no authenticity probability | Automated |
| RISK-02 | Relevant grounded official authorization | Existing lower-risk criteria unchanged; not authenticity verified | Automated |
| RISK-03 | Multiple independent grounded adverse findings / contradictions | Existing conservative risk criteria; conflicts remain explicit | Automated |
| OUT-01 | Evidence insufficient but relevant sources found | Useful promise/unknown summary plus up to two intact labeled links | Automated |
| OUT-02 | Long links, repeated records, mock/partial content | Bound message; no broken citations; labels preserved | Automated |
| OUT-03 | Same fixture assessed through phone and extension | Same promises, decision and uncertainty; format-specific output only | Automated |
| API-01 | Extension route without/incorrect pairing token | Reject before paid provider work; no embedded provider key | Automated |
| API-02 | Unexpected origin / too many or concurrent requests | Reject by configured policy; bounded rate/cost and inflight work | Automated |
| API-03 | Offline default with populated keys | No provider calls on startup or evaluation | Automated |
| EXT-01 | Install unpacked Chrome extension, activate on product page | Pet shown only on user action, no passive research | Manual browser + automated logic |
| EXT-02 | Click Check seller; duplicate click while waiting | One request; Searching animation while pending; no fabricated phases | Automated + manual browser |
| EXT-03 | Successful but insufficient assessment | Finished state and useful promise/source panel; not network error | Automated + manual browser |
| EXT-04 | Failure/timeout/invalid API payload | Error state, explicit retry; no automatic paid retry | Automated |
| EXT-05 | Navigation/dismissal while request pending | No stale result shown on another listing; no promise that costs were reversed | Automated + manual browser |
| EXT-06 | Drag, dismiss, keyboard, reduced motion | Usable controls, movable pet, static motion option; bounded preferences only | Automated where possible + manual browser |
| EXT-07 | Untrusted markup/link/extension message sender | Text rendered safely; only safe source links; hostile tab cannot read pairing/provider secrets | Automated |
| PH-01 | Registered direct inbound, outbound/group/unregistered events | Admit only registered direct inbound text | Automated |
| PH-02 | Duplicate concurrent event / ambiguous send failure | One evaluation/reply attempt; no blind retry | Automated |
| PH-03 | Fresh checkout launch and stop | Documented launcher; hidden/bounded processes; no duplicate listener; clean shutdown | Automated + local manual |
| PH-04 | Live registered-phone URL test | Provider outcomes logged without private content; actual user confirms cited reply receipt | Manual/live, rerun only authorized |
| LIVE-01 | Live extension against real listing | Grok/Tavily source provenance and result panel verified, no screenshot fixture misrepresentation | First run 2026-10-17: promise rows all unavailable (bug). Re-run 2026-10-18 via backend `/api/v1/evaluate-message` on the same Le Labo URL: LOWER_RISK (brand-direct), 4 quoted promise rows; extension panel re-check pending |
| SEC-01 | Git/package/log review | No real .env, phone numbers, credentials, PAN/CVV or browsing history | Automated review |
| OPS-01 | Full regression and setup instructions | Existing tests pass; exact commands/outputs/handoffs recorded | Automated + review |

## Release gates

G1: shared promise contracts and labeled supported/conflict/missing/unavailable fixtures. G2: source-validated backend pipeline and both formatters. G3: offline extension, access controls, reproducible Photon launcher. G4: full regression plus actual browser inspection. G5: explicitly authorized live channel checks and recorded handset/browser receipt. Public hosting, browser-store release and SMS transport are separate unverified gates; do not claim them from local tests.

## Execution log

This file begins as a test plan. Append actual commit, command, output and IDs covered after integration. Manual/live cases remain pending unless explicitly recorded with evidence; historical iMessage receipt does not verify new promise features or the extension.

### 2026-10-17, `main` at `62f1ac8` (docs refresh)

- Command: `python -m pytest -q -p no:cacheprovider` in a fresh macOS Python 3.14 venv with the `pyproject.toml` dependencies => **159 passed**, one Starlette/httpx deprecation warning.
- Node bridge suite not run (Node not installed on that machine); last recorded result 4 passed on Windows.
- Gates: G1 and G2 have automated coverage. G3 was partial at this point (later merges below add the launcher and extension). G4 and G5 are not started for the new features.
- Automated cases with named tests (others not mapped in this pass):
  - PROM-01: `tests/test_policy.py::test_promise_conflict_preserves_risk_and_both_quotes`, `tests/test_sms.py::test_promise_conflict_phone_output_retains_both_quotes_and_links`
  - PROM-04/05: `tests/test_policy.py::test_promise_missing_and_unavailable_are_distinct`, `tests/test_grok.py::test_promise_extraction_missing_client_or_sources_unavailable_not_absent`
  - PROM-06: `tests/test_grok.py::test_promise_extractor_keeps_provider_registry_and_rejects_invented_spans`, `tests/test_policy.py::test_promise_rejects_unproven_spans_and_context`
  - DOM-01/02: `tests/test_research.py::test_rdap_fixed_origin_date_context_and_unsupported_suffix`
  - API-01: `tests/test_api.py::test_extension_pairing_and_origin_before_paid_calls`, `test_extension_unconfigured_and_rate_budget`
  - API-02: `tests/test_api.py::test_extension_concurrent_budget_releases_after_error`, `test_extension_unconfigured_and_rate_budget`
  - OUT-03: `tests/test_api.py::test_end_to_end_promise_conflict_shared_by_extension_and_phone`
- Pending: all EXT-*, LIVE-01, and a PH-04 re-run with the promise sheet.

### 2026-10-17, merge `9c293b8` (Photon launcher)

- PH-03: `app/adapters/spectrum/src/launch.mjs`; `npm test` in `app/adapters/spectrum` => 21 passed (bridge 4 + launcher 17), re-run by the tech lead. Real offline `npm run shop:check` on macOS: API ready, clean stop, no leftover process or lock. Windows `taskkill` path untested; live run pending.

### 2026-10-17, merge `3da454c` (Chrome extension)

- `cd extension && node --test test/*.test.js` => 52 passed (re-run by the tech lead). Offline backend smoke (`extension/scripts/backend-smoke.mjs`): valid token 200, missing/wrong token 401, unlisted origin 403, 429 after five requests. Headless Chrome render check of idle/searching/finished/panel/hostile/error states (scratch harness, not committed).
- Automated: EXT-01 (manifest/injection), EXT-02, EXT-03, EXT-04, EXT-05, EXT-07. Partial: EXT-06 (drag/keyboard movement not exercised).
- Pending manual: unpacked install, service worker lifecycle over a long request, drag/keyboard, reduced motion on a real OS setting, phone-width layout. LIVE-01 pending.

### 2026-10-17, QA rounds 1-3 and fixes

- QA added traceability and adversarial tests (`tests/test_qa_*.py`, `extension/test/qa-*.test.js`, `app/adapters/spectrum/src/qa-*.test.mjs`); nine findings QA-01..09 fixed; human decisions Q1-Q8 recorded in `docs/QA_REPORT.md`. PROM-07 stale terms deferred.
- Final suites: 642 Python passed, 79 extension, 38 Spectrum, 0 xfail/todo. G1-G3 automated; G4 manual browser checks and G5 live runs pending.
