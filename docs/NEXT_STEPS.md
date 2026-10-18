# Current checkpoint and next work

Checkpoint: `main` at `62f1ac8` ("Merge validated packet A integration"), Saturday Oct 17 2026, about 8:50 PM PDT. Both Photon messaging and the Chrome pet extension are core channels sharing one backend (see EXTENSION_SCOPE.md). Do not reset/clean or switch another session's branch.

## Deadlines first

- **Tonight 10:30 PM PDT: mandatory Devpost initial draft.** Humans only: roster, tracks, repo URL, save and confirm. Target 10:00 PM. See SUBMISSION_CHECKLIST.md.
- **Sunday 10:00 AM PDT: final** with playable video and public source. Feature freeze 7:30 AM; target submit 9:15 AM.

## Done (verified in this repository)

- FastAPI app, `.env` loading, offline default, explicit live mode, managed HTTP lifecycle, `dev_server` loopback launcher with `--pair`/`--live`.
- Grok extraction, Tavily research, URL/relevance checks, research status counts, labeled unverified links, deterministic risk policy, SMS/message formatter.
- Promise sheet (G1/G2 in ACCEPTANCE_TESTS.md): D contracts and synthetic fixtures; one bounded Tavily Extract call over up to 3 same-seller pages; Grok promise extraction; Python exact-span validation; supported/conflicting/not_disclosed/unavailable rows; Verisign RDAP registration context for `.com`/`.net` only; image context always unavailable. Both formatters consume the same sheet.
- Extension backend boundary: `POST /api/v1/extension/evaluate` with bearer pairing token, exact origin allowlist, 6 requests/minute and 1 in flight by default. Rejections happen before provider work. The local `/api/v1/evaluate` and `/api/v1/evaluate-message` routes reject any `Origin` header (403) and non-JSON bodies (415) before evaluation (QA Q1).
- Tests: 642 Python, 79 extension, 38 Spectrum tests pass, 0 xfail (macOS, Oct 17). QA ran three rounds (findings QA-01..09 all fixed; see QA_REPORT.md), verdict ready with caveats.
- Live proof: one registered-phone iMessage round trip (Grok, Tavily 5 returned / 2 retained / 3 filtered, VERIFY_FIRST / partial), handset receipt confirmed by the user. This predates the promise sheet; promise extraction and RDAP have not been exercised live.

## Not done

1. **Chrome extension: built offline** (merged `3da454c`). 52 Node tests, real offline backend smoke test, headless Chrome render check. Still needed: manual install checks (see `extension/README.md`: unpacked load, duplicate clicks, navigation mid-request, drag/keyboard, reduced motion, 401/403), phone-width layout, toolbar icon.
2. **Photon launch/stop: done offline.** `npm run shop` in `app/adapters/spectrum` starts the API and `test-bridge.mjs` together with a single-listener lock and clean shutdown (PH-03: 21 Node tests, macOS offline `shop:check` passed; the bridge now gets a least-privilege env without provider keys or the extension token, and `npm test` includes `qa-launch.test.mjs`). Windows path and live run untested.
3. **Live checks of new features.** One authorized live run through the extension (LIVE-01) and one through Photon with the promise sheet (PH-04 re-run). Requires explicit credit/message authorization.
4. **SMS, FastAPI Photon webhook, public hosting, always-on listener.** Unverified; keep out of claims unless done.
5. **Docs/video for submission.** Demo cases (credible evidence vs insufficient evidence), honest real-vs-fixture labeling, team contributions.

## Next implementation, in order

1. Assign the frontend owner and writable path `extension/` (with its assets/tests). Build a Manifest V3 extension against offline fixtures: user activation only (`activeTab`), movable/dismissible pet, Check seller with editable optional price, idle/searching/finished/error states, result panel with risk, decision, summary, missing information, promise rows and up to two labeled links. Text-only rendering, keyboard access, reduced motion, no duplicate in-flight request, stale results cleared on navigation. Pairing token stored in extension storage; provider keys never in the client.
2. Wire the extension to `http://127.0.0.1:8000/api/v1/extension/evaluate` with `channel: "debug"` and the price in `message_text`. Add the unpacked extension ID to `VIZS_EXTENSION_ORIGINS` (otherwise requests carrying an `Origin` header get 403).
3. A: re-verify a registered-phone reply with `npm run shop -- --live` once credentials are on this machine and the run is authorized.
4. Run the automated EXT cases, then one authorized live extension run; record actual results in ACCEPTANCE_TESTS.md.

## Pet and evidence limits

The backend returns one final result with no progress phases. Show Searching for the whole request; do not simulate "Reviewing sources" or percentages. A happy pet is not proof of a safe seller. Preserve deterministic risk, authenticity uncertainty, explicit failures and source provenance. Snippets are never automatic proof.

## Deferred

Pricing/card rewards, DETAILS/history, pet cosmetics, other browsers/categories, image matching, AI-photo detection and advanced infrastructure wait until both channels meet P0.
