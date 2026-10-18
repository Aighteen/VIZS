# QA verification report

Owner: QA/verification session, branch `feat/qa-verification`. All tests use SYNTHETIC data and mocked HTTP transports; no live calls, keys, DNS, messages, push or deployment.

## Resolution (branch `fix/qa-findings`, commit `f61bd76`)

All four findings are fixed, and the tech lead has answered Q1-Q5. The QA xfail and todo markers are removed, so those tests now run as normal tests. Results: `pytest` **362 passed, 0 xfailed**; extension **75 pass**; spectrum `npm test` **35 pass, 0 todo** (it now includes `qa-launch.test.mjs`); `npm run typecheck` is clean.

- **QA-01 fixed** (`app/decision/rules.py`). If official, seller_authorized or verified_fact evidence is hosted on the listing seller's own host, `www.` host or a subdomain of it, it is excluded from authorization. Support from the manufacturer's domain still gives LOWER_RISK.
- **QA-02 fixed** (`app/decision/sms.py`). Inside merchant quotes and conditions, scheme URLs, `www.` hosts and bare domains are replaced with `[link removed]`. These are all forms that messaging apps turn into links. The only links in the reply are the labeled source links, at most two. The rest of each quote is kept.
- **QA-03 fixed** (`app/services/grok.py::_trim_url`). Rule:
  - `,;:!?` at the end of a URL are treated as punctuation.
  - A final `.` is punctuation only at the end of the message, or when the next text starts a new sentence (whitespace then an uppercase letter, or a newline). So `.../perfume. price $20` keeps its dot.
  - A closing `)`/`]`/`}` is kept when it has a matching opener inside the URL, and stripped when unmatched.
  - `'` is part of the URL unless the URL was opened with a quote.
  - Grok's URL must still exactly equal one of the URLs the user supplied.
- **QA-04 fixed** (`app/adapters/spectrum/src/launch.mjs`).
  - The bridge gets an allowlisted env: basic OS/Node variables, proxy/CA variables, `GRPC_*`, `SPECTRUM_IMESSAGE_ADDRESS`, the three Spectrum keys and `VIZS_LOCAL_API`.
  - `XAI_API_KEY`, `TAVILY_API_KEY` and `VIZS_EXTENSION_TOKEN` are not passed to the bridge.
  - Those three values are redacted from output whether they come from the process env, the spectrum `.env` or the root `.env`. A bridge status line that contains one is suppressed.
- **Q1 decided and implemented.** `/api/v1/evaluate` and `/api/v1/evaluate-message` return 403 for any `Origin` header and 415 for any Content-Type other than `application/json`. Both checks run before the body is read. `/api/v1/extension/evaluate` keeps its pairing, Origin allowlist and budget checks, and also requires JSON (415). A body that declares a Content-Length over the cap gets 413 before it is read. One QA assertion changed: `tests/test_qa_security.py` expected 422 for a `{bad` body sent to the extension route without a Content-Type. That request now gets 415 under Q1, and the 422 case is asserted with `application/json`.
- **Q2 decided and implemented.** If extraction is unavailable, times out or returns invalid output after the user sent a URL, the reply says the check could not be completed and to try again later. It does not ask for the URL. If no URL was sent, the reply still asks for one.
- **Q3 decided: deferred.** Detection of stale terms in PROM-07 is out of scope for the hackathon (see ACCEPTANCE_TESTS). The unrelated-seller, region and conflict parts stay covered.
- **Q4 decided and implemented** (`app/decision/promises.py`). A `shipping_origin` row that is supported or corroborated must quote explicit origin wording: ships/shipped/sent/dispatched/dispatches/fulfilled from, warehouse, fulfillment center, or origin. Otherwise the row is downgraded to `not_disclosed` with the explanation "an address is not proof of shipping origin".
- **Q5 decided: no code change.** The "up to two" limit applies to the extension's Sources list. Promise quotes keep their own citation links (EXTENSION_SCOPE result panel bullet). No QA test treated this as open.

New regression tests: `tests/test_qa_fixes.py`, plus a QA-04 test in `app/adapters/spectrum/src/launch.test.mjs`.

## Questions for tech lead (original, answered above)

- **Q1 (security, A).** `/api/v1/evaluate` and `/api/v1/evaluate-message` (`app/api/routes.py:36`, `:55`) have no pairing, Origin check or rate budget, and they parse the body no matter what the Content-Type is. A web page open in the same browser can send a no-preflight `text/plain` POST to `http://127.0.0.1:<port>/api/v1/evaluate`. I verified this with a mocked live-mode probe: it returns 200 and calls Grok, Tavily search, Tavily extract and RDAP. CORS stops the page reading the response, but the paid calls still happen. ACCEPTANCE_TESTS limits API-01/02 to the extension route, so I have not marked this xfail. Should these routes reject requests that carry a browser `Origin` header, require a non-simple Content-Type, or accept only the Spectrum bridge?
- **Q2 (A/D).** When extraction is unavailable, times out or returns invalid output, the phone reply says "Shopping extraction is unavailable; please try again later. [PARTIAL DATA] INSUFFICIENT_EVIDENCE: Send the fragrance listing URL and product context." That asks for a URL the user already sent (`app/decision/sms.py:11` label plus the `app/api/routes.py:60` prefix). Is this the intended wording?
- **Q3 (C/D).** PROM-07 "stale terms": every source's `retrieved_at` is the time of retrieval, and nothing models staleness. What should count as stale?
- **Q4 (B/D).** PROM-03: Python checks only that a quote is an exact span. If Grok labels a business address ("100 Pike Street, Seattle, WA") as a `shipping_origin` merchant statement, it passes validation and is shown as `Merchant statement (shipping origin): "..."`. Should `shipping_origin` rows also need deterministic origin wording ("ships from", "dispatched from", "warehouse")?
- **Q5 (EXT/A).** Link count in the extension panel. The "Sources" list stops at two (`extension/src/lib/view-model.js:9`), but promise-quote links and the RDAP context link are rendered as extra anchors. For the shared OUT-03 fixture the panel shows 4 distinct links, while the phone reply shows 2. Does EXTENSION_SCOPE's "up to two relevant source links" apply to the whole panel, or only to the Sources list, with quoted sources expandable as CREDIBILITY_CHECKING describes?

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

## Phase 2: extension and Photon launcher (merged `main` at 4140998 into this branch)

Commands and results (macOS, Node v26.12.0, Python 3.14 venv):

- `cd extension && node --test test/*.test.js`: baseline **52 pass**. With QA files: **75 pass** (+20 `test/qa-extension.test.js`, +3 `test/qa-cross-channel.test.js`).
- `cd app/adapters/spectrum && npm ci && npm test`: **21 pass**. `npm ci` printed install-script warnings only.
- `cd app/adapters/spectrum && node --test src/*.test.mjs`: **33 pass, 1 todo** (adds 13 tests in `src/qa-launch.test.mjs`; the todo is QA-04). `npm test` lists its files explicitly, so it does **not** run `qa-launch.test.mjs`. A owns `package.json` and would need to add it.
- `python -m pytest -q -p no:cacheprovider`: **309 passed, 5 xfailed** (adds `tests/test_qa_cross_channel.py`: 7 passed, 3 xfailed for QA-03).

New files: `extension/test/qa-extension.test.js`, `extension/test/qa-cross-channel.test.js`, `app/adapters/spectrum/src/qa-launch.test.mjs`, `tests/test_qa_cross_channel.py`, `tests/qa_fixtures/cross_channel_response.json` (backend output generated by the mocked pipeline; a Python test checks it stays in sync), `tests/qa_fixtures/extension_message_texts.json`.

The tech lead confirmed these behaviors and they are now encoded as tests: USD-only `$<amount>` price; evidence labeled "Unverified source" unless `claim_status == verified_fact` ("Verified fact"); promise quotes from `merchant_page` labeled "Merchant's own page", other kinds "Unverified source"; dismiss removes the pet and aborts the fetch.

### Client-side traceability

| ID | Before (existing node tests) | After |
|---|---|---|
| EXT-01 | covered: manifest permissions, click-only injection | + no content_scripts / web_accessible_resources / externally_connectable / broad hosts; loopback-only host permissions |
| EXT-02 | covered: duplicate clicks, "Checking seller…" only | + 6 rapid clicks give one fetch; no background re-check; pet.js string scan finds no reviewing/progress/% wording |
| EXT-03 | covered | + NEED_MORE_INFORMATION (e.g. extraction unavailable) is also finished |
| EXT-04 | weak: HTTP statuses not exhaustively mapped | covered: 15 statuses each give a retryable error, one fetch, explicit retry; malformed payloads give an error |
| EXT-05 | covered | + hash/SPA URL change, lost tab URL, token-mismatch reducer, dismissal aborts the fetch, note never claims costs reversed |
| EXT-06 | weak: reduced-motion only; drag and keyboard not automated | weak (needs manual browser check) |
| EXT-07 | covered: hostile render, sender validation, static token-storage scan | + runtime check that the token never appears in any content-side response or push, for 200/401/403/429/500; markup in every field stays text; only http(s) anchors, max 2 in Sources; label rules |
| PH-01 | covered (bridge-handler) | + group, outbound, foreign sender, non-text, empty, oversized, empty id, null space |
| PH-02 | covered | + thrown send not retried; oversized or malformed output gives the neutral reply |
| PH-03 | covered: lock, shutdown, `--live` only on request | + env never implies `--live`; look-alike flags refused; a second launcher refuses while the first runs and leaves its lock alone; signal during health wait; hard run cap; secrets in argv not echoed; **QA-04** todo |
| OUT-03 (extension side) | missing: extension fixtures were hand-written, not backend output | covered: one backend-generated assessment passes the extension validator; decision, risk, summary, unknowns, promise statuses, explanations and quotes match; every phone-reply link and quote appears in the panel |
| API-01 (client) | covered: bearer header, loopback hosts | + `redirect:"error"`, `credentials:"omit"`; token absent from content side |
| API-02 (client) | weak | covered: one in-flight request per tab; 429 gives a busy error with explicit retry only |

Summary for 13 IDs: before, **9 covered / 3 weak / 1 missing**. After, **12 covered (PH-03 with open QA-04) / 1 weak (EXT-06, manual) / 0 missing**.

### Phase 2 findings

3. **QA-03** (INPUT-01; owner B; EXT could mitigate). `app/services/grok.py:34` (`_URL` stops at `'`) and `:94` (strips trailing `.,;:!?)]}`). Expected: the backend extracts exactly the listing URL the extension sends (`Check this listing <tab href>`). Actual: valid hrefs such as `…/it's-50ml`, `…/perfume-(50ml)` and `…/perfume.` come out truncated. Grok's literal URL is then rejected ("could not safely read"), or a different page is researched. Tests: `tests/test_qa_cross_channel.py::test_INPUT_01_backend_extracts_exact_listing_url_with_punctuation` (3 strict xfails).
4. **QA-04** (PH-03/SEC-01; owner PH). `app/adapters/spectrum/src/launch.mjs:249` passes `{...d.env, ...cfg}` to the bridge, so it receives `XAI_API_KEY`/`TAVILY_API_KEY`, which it does not need. The forwarding filter at `:259` redacts only the three Spectrum values, so a forwarded status line containing a provider key would be printed. Expected: least-privilege bridge env and redaction of every credential. Test: `qa-launch.test.mjs` "provider keys are not handed to the bridge…" (todo). Low severity: the bridge does not print keys today.

Observations: extension `host_permissions` cover only port 8000 (dev_server default). The launcher's API defaults to 8787 and is used by the bridge, not the extension. SEC-01 re-scan after the merge: no new credentials; the only phone-like strings are fictional `+1555…` values in `launch.test.mjs:11,187,192` and the QA tests, all labeled synthetic. The tracked-file test allows only 555 numbers.

## Round 2: independent verification of the fixes (merged `main` at 6d9e512)

### Round 2 questions for tech lead

- **Q6 (D).** QA-01 excludes evidence from the listing host and its subdomains, but not from a parent domain. A listing at `store.synthetic-shop.com` with "official authorization" evidence hosted on `synthetic-shop.com` still gives LOWER_RISK (verified with a probe). That is right if the parent is the manufacturer (for example `store.brand.com` with `brand.com`), and wrong if the parent is the seller's own site. Without public-suffix and ownership data, Python cannot tell the two apart. Should the parent registrable domain also be excluded?
- **Q7 (A).** The Q1 rule covers only `/evaluate` and `/evaluate-message`. With `VIZS_ENABLE_MOCK_SMS=true` and live mode, `/api/v1/mock/messages` still accepts a cross-site `text/plain` POST that has an `Origin`. A mocked probe returned 202 and called Grok, Tavily search, Tavily extract and RDAP. Should the Q1 rule extend to the mock route, or should mock and live be mutually exclusive?
- **Q8 (D).** Q4 is lexical. "100 Pike Street, Seattle. Returns go to our warehouse." keeps a supported `shipping_origin` row because "warehouse" appears, even though here it is about returns. Is this acceptable, or should the origin wording be required in the same sentence as a shipping verb?
- **Choice (b) input for the human.** Replacing bare domains also hits ordinary text: "Chanel No.5 Eau.de Parfum" becomes "Chanel No.5 [link removed] Parfum", and "2-3 days.Free returns" becomes "2-3 [link removed] returns". "Dr.Smith" is replaced entirely. The merchant's own domain inside a quote is replaced too, and the labeled source link stays.

### Round 2 commands and results

| Suite | Fixer's run | After my round-2 files |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider` | **362 passed**, 0 xfailed | **453 passed, 13 xfailed** (new `tests/test_qa_round2.py`: 91 passed, 13 strict xfails) |
| `cd extension && node --test test/*.test.js` | **75 pass** | **77 pass** (new `test/qa-round2.test.js`) |
| `cd app/adapters/spectrum && npm test` | **35 pass**, 0 todo | 35 pass |
| `node --test src/*.test.mjs` | n/a | **38 pass** (new `src/qa-round2.test.mjs`) |

`npm test` lists its files explicitly, so it does not include `qa-round2.test.mjs`. A would need to add it to `package.json`.

### Verification of each fix

| Item | Verdict | Evidence (adversarial cases) |
|---|---|---|
| QA-01 | **fixed** | Seller, `www.`, subdomain, multi-level subdomain, uppercase and trailing-dot hosts never give LOWER_RISK. The manufacturer domain, lookalike `synthetic-shop.com.evil-net.com`, `evil-synthetic-shop.com` and `notsynthetic-shop.com` still can. The parent-domain case is Q6. |
| QA-02 | **fixed for ASCII; gap QA-08** | 14 forms are neutralized in quotes and conditions: scheme in any case, port/query/fragment, `www.`, multi-label, punycode, email, `mailto://`, parenthesized, trailing dot, `javascript://`. The only remaining links are labeled source URLs. Choice (b) behaves as described. Internationalized domains are not neutralized (QA-08). |
| QA-03 | **fixed for prose; gap QA-07** | `(…/p).`, `…/p).`, balanced and multiple parentheses, double-quoted URL, dot then newline, and the extension's `…/perfume. price $20` all follow the documented rule. Seller vs lookalike URLs stay distinct. However, the extension puts the tab href at the very end of `message_text`, so trailing `.` (no price), `?`, `!`, `;`, `:` or an unmatched `)` gets trimmed (QA-07). |
| QA-04 | **fixed** | `NODE_OPTIONS`, `AWS_SECRET_ACCESS_KEY`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, `npm_config_*`, `VIZS_PROVIDER_MODE`, provider keys and the extension token are all withheld from the bridge. Credentials from env, spectrum `.env` and root `.env` are suppressed even inside status-prefixed lines. Env `VIZS_PROVIDER_MODE=live` never adds `--live`. |
| Q1 | **implemented as decided** | Origin `null`, empty, hostile, the allowed extension origin and loopback all give 403 with zero provider calls or DNS. Media-type matching is exact and case-insensitive: `Application/JSON` passes; `json-patch+json`, `merge-patch+json`, a comma list, `text/json` and an empty type give 415. A chunked 40 KB body gets 403/415 before 413. The extension route needs JSON, and its 415s use no budget. The real extension headers are accepted. Node `fetch` (used by the bridge) sends no Origin (loopback probe), so the bridge keeps working. |
| Choice (a) | **behaves as described** | A declared Content-Length over the cap gives 413 before 415 on all three routes. An Origin on a local route still gives 403 first. |
| Q2 | **implemented** | Unavailable, timeout and invalid output, on both evaluate-message and the extension route, say "try again later" and never "send the URL" or "resend". Offline mode does the same. A missing or ambiguous URL still asks for one. |
| Q4 | **implemented; gap QA-06** | Addresses and locations ("Made in France", "Based in New Jersey") become `not_disclosed`, and the address never reaches the phone reply. Explicit wording is kept. Matching is by substring, though (QA-06). The "unrelated part of the quote" case is Q8. |

### Round 2 findings

5. **QA-06** (Q4; owner D). `app/decision/promises.py:265` `_has_origin_wording` uses substring matching, so "**Origin**al packaging", "Ab**origin**al" and "con**sent from**" count as origin wording, and an address-only `shipping_origin` row stays supported. Expected: whole-word or whole-phrase matching. Three strict xfails: `test_Q4_origin_wording_must_be_whole_words`.
6. **QA-07** (INPUT-01/QA-03; owner B, or EXT can mitigate). `app/services/grok.py:_trim_url`, together with `extension/src/lib/request.js:41`, which puts the href last. Valid tab hrefs ending in `.` (no price), `?`, `!`, `;`, `:` or an unmatched `)` are trimmed, so Grok's literal URL is rejected or a different URL is researched. Possible fixes: the extension wraps the URL as `<href>`, which the backend regex already excludes, or always appends trailing text; or the backend skips trimming for the extension channel. Seven strict xfails: `test_QA03_backend_extracts_exact_extension_href_with_trailing_punctuation`.
7. **QA-08** (QA-02; owner D). `app/decision/sms.py:_LINKISH` only matches ASCII labels and TLDs. Homoglyph IDN hosts (`phish-аttacker.com`), Unicode TLDs (`.рф`) and Cyrillic labels pass through unchanged into the phone reply. I could not check iMessage linkification offline, but it auto-links IDN domains. Three strict xfails.

Observations (no xfail):
- QA-03 regression: a possessive after a host ("Is https://shop.com's listing ok?") now yields no URL, because the apostrophe is kept, so the bot asks for a URL.
- Bare IPv4 with a path (`203.0.113.9/claim`) and `tel:` numbers in quotes are not neutralized. Whether they become tappable is not verified.

## Round 2 resolution (branch `fix/qa-round2`, commit `15a9348`)

All round-2 findings and Q6-Q8 were implemented as the human decided. New tests: `tests/test_qa_round2_fixes.py` (82). The 13 round-2 strict xfails are removed and now pass.

| Item | Resolution |
|---|---|
| Q6 / QA-01 | `app/decision/rules.py`: evidence anywhere under the listing seller's registrable domain (seller host, subdomains, parent) never authorizes LOWER_RISK. The registrable domain uses a small built-in list of multi-label public suffixes (`co.uk`, `com.au`, `co.jp`, `com.br`, ...), otherwise the last two labels. **Limitation:** this is not the Public Suffix List. A suffix missing from the list (for example `github.io`, or a rarer second-level ccTLD) makes more hosts count as the seller's site, which can only withhold LOWER_RISK. `store.brand.com` + `brand.com` is now VERIFY_FIRST (accepted). |
| Q7 | `app/api/routes.py`: `/api/v1/mock/messages` returns 404 when disabled (first). When enabled, it applies the same rule as `/evaluate`: any `Origin` gives 403, a declared oversized body gives 413, non-JSON gives 415, all before the body is read. |
| QA-06 / Q8 | `app/decision/promises.py`: origin wording matches whole words/phrases, case-insensitive. "Original", "Aboriginal" and "consent from" no longer count. "warehouse" in an unrelated sentence still counts (accepted, lexical). |
| QA-08 + choice (b) | `app/decision/sms.py`: bare domains in quotes/conditions are neutralized only when they end in a real TLD: a built-in list of common generic TLDs, every two-letter ASCII code, `xn--` punycode, or an all-Unicode TLD (`.рф`). Labels may be Unicode, and `。`, `．`, `｡` count as dots. Scheme URLs, `www.`, `mailto:`/`tel:`/`sms:`/`javascript:`/`data:`, and IPv4 literals (with optional port/path) are always neutralized. "2-3 days.Free returns", "Dr.Smith", "No.5", "U.S." and "$89.99" survive. A non-TLD candidate's path is still scanned, so `days.Free/phish.com` cannot hide a domain. |
| QA-07 | `extension/src/lib/request.js` now sends `Check this listing <URL>[ price $X.XX]`. `app/services/grok.py:_trim_url` treats `<...>` as an exact boundary and trims nothing inside it, so trailing `.`, `?`, `!`, `;`, `:` and an unmatched `)` are kept. The prose rule for phone messages is unchanged. The system prompt tells Grok to return a bracketed URL character for character, and validation still requires the model URL to equal a user-supplied URL. |
| Spectrum tests | `npm test` now includes `src/qa-round2.test.mjs`. |
| Possessive | Fixed (trivial and consistent): a host cannot contain `'`, so an apostrophe in the authority ends the URL. "Is https://shop.com's listing ok?" yields `https://shop.com/`. An apostrophe in a path is still part of the URL (`.../it's-50ml`). |

Test changes (each one follows from a decision):
- `tests/test_qa_round2.py`: removed 3 strict-xfail markers (QA-06, QA-07, QA-08). `extension_message()` now builds the bracketed format, because QA-07 changed the extension's message format.
- `tests/qa_fixtures/extension_message_texts.json`: `message_text` strings use the bracketed format (same reason). The URL and price assertions are unchanged.
- `extension/test/{request,controller,qa-extension,qa-round2}.test.js`: expected `message_text` uses `<URL>` (same reason). No other assertion changed.

**Accepted residual risks (QA-08):**
- Prose whose suffix happens to be a real TLD is still replaced: "Eau.de Parfum" (`.de`), "50ml.It ships" (`.it`), any `word.co`/`word.me`. No common-word heuristic was added, because safety wins.
- Two-letter codes are treated as ccTLDs even when unassigned.
- A real TLD missing from the built-in generic list (for example `.boutique` is listed, `.free` and `.new` are not) is not neutralized when written without a scheme or `www.`. iMessage linkification of such text was not verified offline.
- Phone numbers without `tel:` are not neutralized.

Commands on `fix/qa-round2`:
- `python -m pytest -q -p no:cacheprovider`: **548 passed**, 0 xfailed.
- `cd extension && node --test test/*.test.js`: **77 pass**.
- `cd app/adapters/spectrum && npm ci && npm test`: **38 pass**, 0 todo (includes `qa-round2.test.mjs`).

## Round 3: verification of the round-2 fixes and final readiness (merged `main` at 22b3d9b)

### Round 3 questions for tech lead

None blocking. QA-09 below has a clear fix. Accepted residuals (ccTLD-like prose, word-level "warehouse", small suffix list, unassigned two-letter codes) were not re-tested as defects.

### Round 3 commands and results

| Suite | Fixer's run | After my round-3 files |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider` | **548 passed**, 0 xfailed | **641 passed, 1 xfailed** (new `tests/test_qa_round3.py`: 93 passed, 1 strict xfail QA-09) |
| `cd extension && node --test test/*.test.js` | **77 pass** | **79 pass** (new `test/qa-round3.test.js`) |
| `cd app/adapters/spectrum && npm test` | **38 pass**, 0 todo | 38 pass; `package.json` now includes the QA files |

No process was started on port 8000 or any other port. No live calls were made and no `.env` file was read.

### Verification of the round-2 fixes

| Fix | Verdict | Adversarial cases tried |
|---|---|---|
| Q6 registrable domain | **fixed** | `co.uk`, `com.au`, an unlisted `com.fj` fallback (over-inclusive, so it can only withhold LOWER_RISK), IPv4 hosts, uppercase, `www.` and trailing dot. Seller host, subdomain and parent never give LOWER_RISK. Siblings under a public suffix (`brand.co.uk` next to `myshop.co.uk`), lookalikes (`myshop.co.uk.evil-net.com`, `seller.com.evil-net.com`, `evilseller.com`) and a neighbouring IP still can. |
| Q7 mock route | **fixed** | An Origin header (hostile, `null`, extension) gives 403. `text/plain`, a missing type and `json-patch+json` give 415. Origin plus text gives 403. When the route is disabled, it returns 404 for any request. Declared and chunked oversized bodies give 413. In every case there are zero provider calls and nothing is sent. Local JSON still works and stays labeled `MOCK SIMULATION`. |
| QA-06 origin wording | **fixed** | Newline, NBSP and multiple spaces inside phrases, "Country of origin:", "Origin:" and "warehouse" are recognized. "Original", "Originally", "Aboriginal", "consent from", "warehouses", "Shipsfrom" and "origins" are not. |
| QA-08 link neutralizing | **fixed** | Neutralized: Cyrillic homoglyph host, ideographic/fullwidth/halfwidth dots, fully fullwidth `ｅｖｉｌ．ｃｏｍ`, `xn--` labels and TLDs, IPv4 with and without port or path, email, `tel:`, `sms:`, `facetime:`, `data:`, uppercase, multi-label, `.co.uk`, pseudo-path smuggling (`days.Free/phish.com`) and Unicode label plus TLD. "2-3 days.Free", "Dr.Smith", "No.5", "Version 2.5" and "50ml.Thanks" survive. Pathological 1200-character inputs finish in under 0.5 s. A mixed attack quote leaves exactly one labeled link and six `[link removed]`. |
| QA-07 brackets | **fixed** | `<…?>` and `<…).>` stay exact. A bracketed URL followed by `.` works. Two URLs joined with brackets still count as two, so the bot asks for clarification rather than silently picking one. A real tab href cannot contain a raw `<`, `>` or whitespace (node test). A 2048-character URL with a trailing `.` fits under 4000 characters and is researched verbatim end to end. A trailing-dot listing sent through the extension route reaches research unchanged. The phone prose rule is unchanged (the original QA-03 cases re-run). |
| Possessive URLs | **fixed** | `https://shop.com's` and `https://shop.com:443's` give the host. The in-path `it's-50ml` and the bracketed `<…/p's>` are kept. A quoted URL is trimmed. |

### Round 3 finding

8. **QA-09** (RISK-03; owner D). `app/decision/rules.py`: the `adverse_hosts` set counts hosts, so two adverse findings from `a.regulator-synthetic.gov` and `b.regulator-synthetic.gov` are treated as two independent sources and give HIGHER_RISK/AVOID. Expected: "multiple independent grounded adverse findings" (RISK-03, API_CONTRACTS) should count distinct registrable domains, for example `registrable_domain(e.source_url.host)`. Two different registrable domains still give HIGHER_RISK (passing control test). Low severity: the research layer never emits grounded adverse evidence today. Test: `test_RISK_03_adverse_findings_from_one_registrable_domain_are_not_independent` (strict xfail).

### Whole-project P0 pass: requirements not verified by an automated test

| P0 requirement (source) | Automated status | Manual or live check that covers it instead |
|---|---|---|
| Extension loads unpacked in Chrome; pet appears only after a toolbar click (EXTENSION_SCOPE P0-1, EXT-01) | Only the manifest and background logic are tested | G4: load unpacked, click the toolbar on a listing, and confirm there is no injection or network activity before the click |
| Pet is movable (drag and arrow keys) and dismissible, keyboard reachable, with a static pet under reduced motion (P0-4, EXT-06) | Weak: the reduced-motion flag and CSS are tested; `pet.js` drag, keyboard and focus handling have no automated test | G4 manual browser check, including OS reduced-motion |
| Content-side stale guards in `pet.js` (SPA href polling, stale push drop, `resetToIdle`) (EXT-05) | Service-worker side is fully tested; `pet.js` logic is not run in tests | G4: start a check, navigate within the SPA and by full navigation, and confirm no old result appears |
| Result panel layout and readability on real pages (P0-5) | Renderer tested with a fake DOM | G4 visual check on two or three real listing pages |
| One authorized live extension run (P0-8, LIVE-01) | Not automatable | G5: authorized live run with recorded provenance |
| Photon registered-phone cited reply with the promise sheet (P0, PH-04) | Bridge logic and launcher tested with fakes | G5: authorized `npm run shop` run with handset receipt confirmed by the user |
| Reproducible launcher on a real machine (PH-03) | Fully faked in tests | `npm run shop:check` on the demo machine (offline, starts the API on 8787; not run here to avoid reading `.env`) |
| SMS transport, public hosting, FastAPI Photon webhook (AGENTS P0 "verify SMS separately") | Out of scope; `/webhooks/photon` returns 503 (tested) | Not verified. Do not claim them. |
| Real Grok/Tavily behavior (promise extraction quality, source relevance) | Mocks only | G5 live run; quality is not provable offline |

Covered by automated tests across the three suites: AGENTS hard limits (no authenticity or fraud percentage, no accusations, LOWER_RISK never from snippets or self-assertion, discount never HIGHER_RISK, prompt injection, SSRF, keys server-side, no phone or secret leakage, labeled mock data); EXTENSION_SCOPE P0-2, 3, 5, 6, 7 (logic); and the CREDIBILITY_CHECKING deterministic response rules (span validation, unknown vs unavailable, region and seller matching, no invented costs, context signals do not change risk, at most two phone links, safe rendering).

### Readiness verdict

**Ready with caveats.** All three suites are green: 641 passed plus 1 tracked xfail, 79 pass, and 38 pass. Every QA finding from rounds 1-2 (QA-01..08) is fixed and independently verified, and Q1-Q8 are decided. Remaining caveats:
1. QA-09 is open. It is low severity because the current pipeline cannot produce grounded adverse evidence, and the fix is one line.
2. Release gates G4 (actual browser inspection, EXT-06) and G5 (authorized live extension and iMessage runs) are not done. They are required before claiming those behaviors in the submission.
3. SMS, hosting and the FastAPI Photon callback remain unverified by design.
