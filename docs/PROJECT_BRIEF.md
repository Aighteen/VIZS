# Project brief - fragrance shopping assistant through Photon and an animated browser pet

Current user-approved direction: both Photon messaging and a Chrome extension with an animated on-page shopping pet. They are core channels sharing the existing evidence-backed backend. See EXTENSION_SCOPE.md for acceptance criteria and boundaries and NEXT_STEPS.md for current status. The backend, extension route and MV3 extension exist; live runs are pending.

## Credibility-checking update from the supplied Kept brief

Use a promise-first explanation: what the merchant promises, what retrieved sources say, and what remains unknown. Topics: shipping origin, processing/arrival estimates, return destination/cost/conditions, domain-registration context and photo reuse. AI-photo detection remains deferred without validated model evidence. Each line needs genuine source provenance and quoted spans; merchant wording is not proof of fulfillment. See CREDIBILITY_CHECKING.md for contracts, rules, staged tasks and exclusions. Implemented: shipping/arrival/returns promise rows with validated quotes and `.com`/`.net` registration context. Image reuse and AI-photo checks report unavailable. Both Photon and the extension remain core; the reference's broader payments/tracker/training scope is not adopted.

## Customer and problem

Fragrance shoppers need to judge seller credibility without treating unknown sellers, gray-market listings or large discounts as proof of fraud. The assistant should offer actionable advice with traceable sources and honest uncertainty while they browse.

## Browser journey

1. Open a fragrance product listing and activate the extension.
2. Click the pet's Check seller button; submit the page URL and optional confirmed price.
3. Pet shows Searching while FastAPI runs Grok extraction, Tavily research, source validation and deterministic Python policy.
4. Pet signals completion; its panel shows seller risk, buying advice, source links and remaining unknowns.
5. If evidence is weak, show VERIFY_FIRST with unverified references and verification steps. Failures have separate error/retry states.

## Photon journey

A registered shopper messages a listing URL and optional price; Photon carries the assessment back with source links and uncertainty. It uses the same backend and decision policy as the extension. Preserve the confirmed iMessage flow; SMS and public/persistent deployment still need verification.

## P0 - both channels

- Reproducible Photon launch/stop, registered inbound evaluation and cited reply, with duplicate/failure handling.
- Chrome extension with on-page pet and compact result panel.
- User-triggered active-page URL capture; optional editable price.
- Honest idle/searching/finished/error states; reviewing-sources animation only with a real backend phase signal.
- Keyboard access, movable/dismissible pet and reduced-motion support.
- Existing FastAPI/Grok/Tavily/policy pipeline reused; API keys remain server-side.
- Safe backend access, bounded requests and source rendering before public use.
- Offline fixture coverage and one authorized live extension assessment.

## Implemented foundation

Packets A-D, runtime wiring, the promise sheet and the extension route are on `main` at `62f1ac8`. Last check: 159 Python tests passed (Oct 17); Node bridge suite last recorded 4 passed. Registered-phone iMessage -> Grok -> Tavily -> policy -> cited reply was confirmed received by the user (before the promise sheet). The MV3 extension is merged at `3da454c` and offline-tested. Current snippets remain unverified; stronger official-source validation is still needed for useful stronger conclusions.

## Photon channel and deferred work

Photon messaging remains core; retain the tested bounded Spectrum iMessage bridge and add a reproducible launch/stop flow. It is not verified SMS or an always-on deployed service. Pricing comparisons, card rewards, DETAILS/history and additional browsers/product categories are P1 only after both-channel P0. Pet cosmetics and multiple pets are deferred.

Autonomous purchasing, banking linkage, payment credentials, massive scraping, fine-tuning, fraud percentages and multi-agent infrastructure are outside scope.

## Correctness and privacy

LOWER_RISK does not verify authenticity. HIGHER_RISK is not a legal fraud finding. Unknown authorization and low price are not counterfeit proof. Reviews/snippets remain allegations or unknowns until grounded. Every factual reason must trace to an actually returned source. No secrets or sensitive payment data in the extension, page scripts, Git or SMS. No passive browsing-history collection.

## Human decisions and event constraints

Assign the new extension owner, choose pet appearance, and decide backend hosting/access configuration. Humans still finalize title/side tracks and submit. Both-channel scope does not establish sponsor eligibility. Mandatory draft/final deadlines and coding-window constraints in SPRINT_PLAN.md remain unchanged; preserve upload buffers.
