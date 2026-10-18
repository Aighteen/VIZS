# Current scope: Photon messaging and a browser extension with an animated pet

Approved direction: the user wants both Photon messaging and a Chrome extension with an animated on-page pet that shows when research is running. Both channels are core scope and share the existing assessment backend. Status at `3da454c`: the backend extension route, pairing and request budget, and the MV3 extension in `extension/` are implemented and offline-tested. Manual Chrome install checks and a live run are pending. Adding the extension does not replace or downgrade Photon.

## Product and first release

An online shopper opens a product listing, activates the extension, and clicks the pet's "Check seller" action. The extension submits the current page URL and an optional user-confirmed price. The backend returns seller risk, buying advice, relevant source links, missing information and an optional `promise_sheet` with quote-validated shipping, arrival and returns rows plus domain/image context (image is always unavailable). See CREDIBILITY_CHECKING.md and API_CONTRACTS.md. Clicking the pet opens a compact on-page result panel. Any product category is supported; testing so far has mostly used fragrance listings.

The pet is the extension's own mascot. There is no required Codex API, ChatGPT Work Pets integration, or account connection. Its appearance is still to be chosen; a code-native simple mascot can be used first. Pet behavior communicates request progress, never seller trust before the assessment completes.

| State | Behavior | Trigger |
|---|---|---|
| Idle | Calm pet with Check seller action | No active request |
| Searching | Searching/walking animation and working text | Submitted request awaiting response |
| Reviewing sources | Reading/thinking animation | Only when a real backend phase signal exists |
| Finished | Notification bubble opens result | Valid completed assessment, including insufficient evidence |
| Error | Puzzled pet, plain error and explicit retry action | Failed, unavailable, or timed-out request |

The existing backend returns a single final response and has no streaming phase signals. MVP may show Searching throughout the request; it must not simulate a source-review phase or percentage completion. No new progress infrastructure is required just for the animation.

## Photon journey and shared behavior

A registered user sends a product listing URL and optional price through Photon. The same Grok/Tavily/Python workflow returns the same risk policy, labeled sources and unknowns as the extension, formatted for a message. Maintain source/status clarity, bounded calls, duplicate protection and explicit failure handling. The pet is a browser UI; it does not need to appear in the phone conversation.

P0 includes a reproducible Photon launch/stop flow and verified inbound/reply behavior alongside the extension UI. Existing proof is iMessage; do not call it SMS. Public hosting, a persistent listener and a verified FastAPI callback remain unfinished. Shared assessment logic is required; cross-channel account linking, history synchronization and automatic forwarding between channels are not required.

## P0 acceptance criteria for both channels

- Chrome extension loads locally; user activation shows a small movable/dismissible pet on the current shopping page. No automatic research on navigation.
- Check seller captures the active listing URL; optional price is editable/confirmed. Do not scrape the entire page, payment forms or account details.
- One user action starts one bounded backend evaluation. Repeated clicks do not silently create duplicate paid calls. Navigation/dismissal clears stale results; cancellation does not promise reversal of already incurred provider work.
- Searching animation runs until the request settles. Keyboard access and reduced-motion/static pet behavior work. Position/visibility preferences may be local; no purchase/browsing history storage is required.
- Result panel shows risk, decision, summary, missing information, provider failure states and up to two relevant source links. The "up to two" limit applies to the Sources list; each promise quote keeps its own citation link (and the domain context keeps its RDAP link), as CREDIBILITY_CHECKING describes. Unverified sources remain labeled. Distinguish completed insufficient evidence from a failed request.
- Provider keys stay on the server. Implemented locally: `POST /api/v1/extension/evaluate` requires `Authorization: Bearer <VIZS_EXTENSION_TOKEN>`, rejects `Origin` values not in `VIZS_EXTENSION_ORIGINS`, and limits to 6 requests/minute and 1 in flight by default, all before provider work. This is local pairing, not public authentication; the API is not production-ready.
- Extension permissions are limited to the user-triggered page/task. Merchant/page content is untrusted and cannot change system instructions, tools or risk policy. Link opening/rendering must not execute retrieved markup or instructions.
- Verify offline fixture cases first, then one explicitly authorized live extension run. An offline fixture or animated demo is not evidence of live Grok/Tavily usage.

## Reused backend and current proof

Python/FastAPI, shared Pydantic contracts, Grok extraction, Tavily, source/URL validation, deterministic risk rules, research status counts, evidence labels, the promise sheet and the extension route are implemented. The extension calls POST /api/v1/extension/evaluate, which returns `{assessment, message_text}`; the body still uses channel=debug because there is no extension channel in the contracts. Do not invent channel=extension without a D-owned contract change. A owns the client-facing boundary/access configuration; D owns schema changes. Optional supplied price is extracted from message_text, not a separate request field.

Last checks: 159 Python tests passed on Oct 17 (macOS, fresh venv); Node bridge suite last recorded 4 passed. A real registered-phone iMessage test produced five Tavily records, two retained, three filtered, VERIFY_FIRST/partial; user confirmed receipt with unverified links. That proves the phone path before the promise sheet was added, not the extension.

Photon messaging is a core product channel alongside the extension. Existing Spectrum iMessage bridge is bounded/local and stopped. SMS transport, the FastAPI Photon callback, persistent service and public deployment remain unverified. Keep historical proof accurate if humans consider the Photon track.

## Deferred or excluded

After P0 only: exact-match pricing, card rewards using non-sensitive labels, DETAILS/history, pet cosmetics or multiple pets, other browsers, richer genuine progress signals. Excluded: autonomous checkout/payment, PAN/CVV/banking linkage, authenticity certainty or fraud probabilities, massive scraping, multi-agent infrastructure. No browser-store publication or deployment is authorized by this scope update.

## Ownership and next implementation tasks

Frontend area: extension/ including its assets and tests. TECH_LEAD_PLAN.md assigned it to a local `feat/pet-extension` worktree, but nothing has been pushed or merged; confirm the owner before coding. A owns Photon integration, backend access configuration and coordination; B/C/D retain their modules. Document an explicit frontend session assignment before coding and use a separate checkout for concurrent editing.

Next: confirm the frontend owner and implement a minimal Chrome extension/pet shell plus offline result-panel fixtures against the existing extension route. In parallel only when explicitly requested: A adds a reproducible Photon launch/stop flow. Acceptance tests should cover request/state transitions, error/insufficient-evidence distinction, duplicate-click handling, safe rendering, keyboard/reduced motion, and backend access enforcement. Then test one real listing against the shared backend and record actual results.

## Credibility reference update

Adopt the user-supplied Kept brief only for the promise-first credibility method described in CREDIBILITY_CHECKING.md. Both channels remain core. The extension panel will present merchant wording, quoted evidence, contradictions and unknowns; Photon will summarize the same result. Broader checkout, tracking, timestamping, training and dispute features are not added.
