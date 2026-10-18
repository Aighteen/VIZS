# QA verification report

Owner: QA/verification session, branch `feat/qa-verification`. All tests use SYNTHETIC data and mocked HTTP transports; no live calls, keys, DNS, messages, push or deployment.

## Questions for tech lead

- **Q1 (security, A).** `/api/v1/evaluate` and `/api/v1/evaluate-message` (`app/api/routes.py:36`, `:55`) have no pairing, Origin check or rate budget, and they parse the body no matter what the Content-Type is. A web page open in the same browser can send a no-preflight `text/plain` POST to `http://127.0.0.1:<port>/api/v1/evaluate`. I verified this with a mocked live-mode probe: it returns 200 and calls Grok, Tavily search, Tavily extract and RDAP. CORS stops the page reading the response, but the paid calls still happen. ACCEPTANCE_TESTS limits API-01/02 to the extension route, so I have not marked this xfail. Should these routes reject requests that carry a browser `Origin` header, require a non-simple Content-Type, or accept only the Spectrum bridge?
- **Q2 (A/D).** When extraction is unavailable, times out or returns invalid output, the phone reply says "Shopping extraction is unavailable; please try again later. [PARTIAL DATA] INSUFFICIENT_EVIDENCE: Send the fragrance listing URL and product context." That asks for a URL the user already sent (`app/decision/sms.py:11` label plus the `app/api/routes.py:60` prefix). Is this the intended wording?
- **Q3 (C/D).** PROM-07 "stale terms": every source's `retrieved_at` is the time of retrieval, and nothing models staleness. What should count as stale?
- **Q4 (B/D).** PROM-03: Python checks only that a quote is an exact span. If Grok labels a business address ("100 Pike Street, Seattle, WA") as a `shipping_origin` merchant statement, it passes validation and is shown as `Merchant statement (shipping origin): "..."`. Should `shipping_origin` rows also need deterministic origin wording ("ships from", "dispatched from", "warehouse")?

## Phase 1 commands and results (backend)

- Baseline at `f4aabeb`: `python -m pytest -q -p no:cacheprovider` gave **159 passed**, 1 Starlette deprecation warning.
- After the QA additions: **302 passed, 2 xfailed** (145 new: 111 passed and 2 xfailed in `tests/test_qa_acceptance.py`, 32 passed in `tests/test_qa_security.py`).

New files: `tests/test_qa_acceptance.py`, `tests/test_qa_security.py`, `tests/qa_fixtures/{README.txt,shipping_ranges.json,injection_pages.json}` (all labeled SYNTHETIC).

## Traceability (backend-automatable IDs)

Before means the existing tests at `f4aabeb`, judged on their assertions. After includes the `test_qa_*` files.

| ID | Before | Existing evidence / gap | After (new tests) |
|---|---|---|---|
| INPUT-01 | covered | test_grok success binding; test_api assembled pipeline | + e2e `test_INPUT_01_*` (identity, price, one search, backend query) |
| INPUT-02 | covered | test_grok missing/ambiguous; test_api offline | + live e2e with zero provider/DNS calls |
| INPUT-03 | covered | test_grok untrusted output, tool_calls | + e2e: invented URL/task/price/brand/tool_call, only the plan call happens |
| INPUT-04 | weak | refusal untested | covered: refusal, 500, 401, invalid JSON, sanitized |
| PROM-01 | covered | policy/sms/api conflict tests | + accusation and probability scan of both formats |
| PROM-02 | missing | none | covered: distinct processing/transit, no guarantee, merged or invented ranges rejected |
| PROM-03 | missing | none | weak/flagged: deterministic path covered; model-inference path is Q4 |
| PROM-04 | weak | snippet-only registry untested | covered |
| PROM-05 | weak | unit only | covered: e2e Extract 503 gives all unavailable, no promise call, risk unchanged |
| PROM-06 | covered | test_grok/test_policy span rejection | + model-supplied `sources` rejected |
| PROM-07 | weak | foreign-host merchant page, substituted extract untested | covered except "stale" (Q3) |
| PROM-08 | missing | none | covered; **QA-01** xfail |
| PROM-09 | weak | validator-level only | covered: e2e tool counts, fixed system prompt, allowed hosts; **QA-02** xfail |
| PROM-10 | weak | missing-quote rows untested | covered |
| RES-01 | covered | 3/1/2 variant | + exact 5/2/3 case |
| RES-02 | covered | test_api parametrized | n/a |
| RES-03 | covered | test_api missing key / failures | n/a |
| RES-04 | covered | snippet param | + extractor-level snippet rejection |
| RES-05 | weak | URL count, size and timeout untested | covered |
| RES-06 | covered | test_url_safety | + IPv6 ULA/link-local, CGNAT, octal, mixed IPv6 DNS, e2e unsafe_url |
| DOM-01 | covered | test_research RDAP | + e2e context wording |
| DOM-02 | weak | 404/timeout/naive/ambiguous untested | covered |
| IMG-01 | covered | e2e image_context | + model photo/AI-photo rows rejected |
| RISK-01 | weak | young domain, reviews-only untested | covered |
| RISK-02 | covered | test_official | + wording |
| RISK-03 | covered | test_independent_adverse_and_conflict | + explicit conflict wording |
| OUT-01 | weak | "up to two links" not asserted | covered (see QA-02) |
| OUT-02 | weak | promise quote truncation untested | covered at 350/600/1000 budgets |
| OUT-03 | weak | existing test's second call is served from the workflow cache (`app/workflow/service.py:43`), so the pipeline is not re-run | covered with two fresh pipelines |
| API-01 | weak | run in offline mode, so "before provider work" is not observable | covered in live-mocked mode: zero calls/DNS, auth before body, 413 |
| API-02 | covered | unit concurrency/rate | + ASGI concurrent e2e, window reset, config bounds |
| API-03 | weak | DNS not detectable | covered with socket patching |
| PH-02 | covered | test_jobs, simulator | + triple duplicate, label |
| SEC-01 | weak | Settings repr only | covered: logs, responses, reprs, tracked-file scan, ignore rules |
| OPS-01 | covered | suite | n/a |

Summary for 35 IDs: before, **18 covered / 14 weak / 3 missing**. After, **33 covered (2 with open defects) / 2 weak-flagged (PROM-03, PROM-07 stale) / 0 missing**. EXT-03/04 backend side (insufficient = 200; failures = 502/504; budget released; no retry) is added in `test_EXT_03_04_*`. The EXT client, PH-01 and PH-03 are covered in phase 2 below.

## Findings

1. **QA-01** (PROM-08; owner D). `app/decision/rules.py:25`. Expected: the seller's own page asserting authorization never counts as manufacturer corroboration (CREDIBILITY_CHECKING "A shop's self-asserted authorization is not manufacturer corroboration"; ARCHITECTURE rule 1). Actual: an `official`/`seller_authorized`/`verified_fact` Evidence whose `source_url` host equals the seller host gives LOWER_RISK/CONSIDER_BUYING. The current research layer never emits such evidence, so this is a defense-in-depth gap. Test: `test_PROM_08_seller_hosted_official_authorization_cannot_yield_lower_risk`.
2. **QA-02** (PROM-09, OUT-01; owner D). `app/decision/sms.py:43`. Expected: at most two labeled links, and only links to retrieved sources. Actual: a merchant quote that contains a URL (for example an injected `http://phish.attacker.com/claim`) is copied verbatim into the phone reply, where iMessage makes it a clickable, unlabeled third link. Test: `test_PROM_09_link_inside_merchant_quote_is_not_rendered_as_extra_link`.

Observations (not marked xfail): the root `.gitignore` covers `.env` at any depth but not `.env.local` or `.env.*`. The README `.env.example` sample differs from the tracked file (placeholders in both).

## SEC-01 static review (phase 1)

- Tracked env-like files: only `.env.example` and `app/adapters/spectrum/.env.example`. Git history (`git log --all --name-only`) has no other `.env`, log, key or database files.
- Credential pattern scan (xai-/tvly-/sk-/AKIA/private key/GitHub token/assigned secrets): two hits, `.env.example:8` and `.env.example:11`. Both values are lowercase "replace…your…" placeholders with no digits, so they are false positives. No values were printed.
- Phone, PAN (Luhn-checked) and CVV patterns: 0 hits. The only email-like strings are test URLs with userinfo (`tests/test_grok.py:54`, `tests/test_url_safety.py:9`).
- Ignore rules: `.env`, `extension/.env` and `app/adapters/spectrum/.env` are ignored. `.env.local` at the root is not.
- App code contains no `logging` calls. `dev_server` prints a fixed message with no token value.
