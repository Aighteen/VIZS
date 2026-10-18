# Tech lead handoff

For any AI coding tool (Claude Code, Codex, Cursor, Copilot) or person taking over coordination. Snapshot: Saturday Oct 17 2026, late evening PDT, local `main` at `506e562`. Nothing has been pushed to GitHub since `62f1ac8`.

## Read first

1. `AGENTS.md` (rules: no paid calls, pushes, deployment or submission without the human's instruction; never print secrets)
2. `docs/NEXT_STEPS.md` (status and remaining work)
3. `docs/QA_REPORT.md` (traceability matrix, findings QA-01..08, decisions Q1-Q8)
4. `docs/ACCEPTANCE_TESTS.md` (case IDs and execution log)

## How the work was run

The tech lead session split work into git worktrees under `.claude/worktrees/` (ignored), one branch per agent, then reviewed, re-ran tests and merged with `--no-ff` into local `main`. Agents never asked the human directly: questions went to the tech lead, who asked the human and relayed answers. Keep that pattern: agents write only their assigned paths, mark confirmed product defects as strict `xfail` (Python) or `todo` (Node) until fixed.

| Branch | State |
|---|---|
| `docs/status-refresh`, `feat/photon-launcher`, `feat/pet-extension`, `feat/qa-verification`, `fix/qa-findings` | Merged into `main` |
| `fix/qa-round2` | Merged at `506e562` (548 / 77 / 38 tests, 0 xfail). QA round 3 (final verification + readiness verdict) was in progress on `feat/qa-verification` at handoff |

### `fix/qa-round2` brief (human-decided)

1. Evidence anywhere under the seller's registrable domain (host, subdomains, parent) never counts toward LOWER_RISK (`app/decision/rules.py`).
2. `/api/v1/mock/messages` gets the same lockdown as `/api/v1/evaluate`: Origin → 403, non-JSON → 415, before reading the body; 404 when disabled stays first.
3. Shipping-origin wording matches whole words only (`app/decision/promises.py`); word-level "warehouse" in a returns sentence is accepted.
4. Phone-reply quote link neutralizing only for real TLDs plus Unicode/punycode hosts (`app/decision/sms.py`); "days.Free" and "Dr.Smith" must survive; "Eau.de" residual accepted.
5. Extension wraps the tab URL as `Check this listing <URL>` (+ ` price $X.XX`) so trailing `.?!;:)` are kept (`extension/src/lib/request.js`, backend `_trim_url`).
6. Add `src/qa-round2.test.mjs` to `npm test` in `app/adapters/spectrum/package.json`.
7. Possessive `https://shop.com's` URL: fix only if trivial.
(Done; kept for reference.) After any extension change, reload it in `chrome://extensions`.

## Test commands (macOS)

```sh
python -m pytest -q                                   # 642 passed (QA rounds 1-3 merged, QA-09 fixed)
cd extension && node --test test/*.test.js            # 79 pass
cd app/adapters/spectrum && npm ci && npm test        # 38 pass
```

This machine has no project `.venv`; the tech lead used a scratch venv. Create one with `python3 -m venv .venv && .venv/bin/python -m pip install -e '.[test]'`. Node v26 is installed via Homebrew.

## Live runs (human authorized one extension run and one Photon run)

- Root `.env` has xAI/Tavily keys, `VIZS_EXTENSION_TOKEN` (last line) and `VIZS_EXTENSION_ORIGINS=chrome-extension://dlnlglldnffdopenfjkjfdffhefmpkoh`. Provider mode in the file is offline; live only via `dev_server --live`.
- At handoff a live backend may be running on port 8000 (`python -m app.workflow.dev_server --live --port 8000`), started by the tech lead session; it stops when that session ends. Check with `curl http://127.0.0.1:8000/healthz`.
- LIVE-01 (extension): human loads `extension/` unpacked, pastes the token, clicks Check seller once on a real listing. Result not yet recorded; ask the human and add it to `docs/ACCEPTANCE_TESTS.md`.
- PH-04 (Photon): needs `app/adapters/spectrum/.env` with `PROJECT_ID`, `PROJECT_SECRET`, `VIZS_REGISTERED_RECIPIENT` (missing at handoff). Then `cd app/adapters/spectrum && npm run shop:check && npm run shop -- --live`.

## Remaining before Sunday 10:00 AM PDT final

- Record LIVE-01 and PH-04 results.
- Manual extension checks listed in `extension/README.md` (drag/keyboard, reduced motion, navigation mid-request).
- Update README/NEXT_STEPS status, then push to GitHub **only when the human says so**, verify the public repo has no secrets.
- Human-only: Devpost draft (was due Sat 10:30 PM), video, final submission by 9:15 AM target.

## LIVE-01 result and open bug (latest)

Live extension run on Le Labo's own store (`https://www.lelabofragrances.com/santal-33-147.html?...` with ~250 chars of ad-tracking params: gclid, gbraid, gad_*). Panel: INSUFFICIENT_EVIDENCE / VERIFY_FIRST, partial data; Tavily search 5 of 5 kept (two Le Labo pages: Terms & Conditions of Sale, Cancellation Rights FAQ, shown as unverified snippets); RDAP context returned; **all five promise rows "Could not be checked"** (unavailable). Record this in ACCEPTANCE_TESTS as LIVE-01 (completed, promise extraction not working live).

Two problems, fixes proposed but NOT yet approved by the human (ask before building):

1. **Brand selling on its own site can never get LOWER_RISK.** Side effect of QA-01/Q6 (seller-own-domain evidence never counts, `app/decision/rules.py` `_same_site`). Proposed: brand-direct rule when independent evidence confirms the listing domain is the brand's official site; must not let lookalikes (`lelabo-outlet-sale.com`) through.
2. **Promise rows empty live.** Pipeline: `app/research/promises.py` collect_promise_sources (listing + same-seller search URLs, max 3) -> `app/services/tavily.py` extract_sources -> `app/workflow/runtime.py` resolve_promises (Grok promise client only if a `merchant_page` record exists) -> `app/research/promise_extractor.py` -> `validate_promise_sheet`. Failures are silent (exceptions swallowed, no stage status). Prime suspect: `tavily.py` line ~111 drops any extract result whose returned URL is not exactly in `admitted`; Tavily likely normalizes the long tracking URL, so the listing page is discarded. Other suspects: Grok spans not exact, 15-20 s timeouts.
   Proposed fix: (a) strip tracking params (gclid, gbraid, wbraid, gad_*, utm_*, fbclid, msclkid, source=shoppingads) from the listing URL before research; (b) accept extract results for the same host+path differing only in tracking params; (c) add privacy-safe promise-stage diagnostics (extract status, pages returned, Grok called, rows kept/rejected) surfaced in the row explanations; (d) brand-direct rule above; (e) one more authorized live re-run of the same URL.

The live backend on port 8000 was started by the previous session and stops with it. Restart: `python -m app.workflow.dev_server --live --port 8000` (root `.env` already has keys, token and extension origin).
