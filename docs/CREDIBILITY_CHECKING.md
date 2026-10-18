# Credibility checking: promises and evidence

## Source and scope

The user supplied the Kept project brief as the desired credibility-checking reference. Adopt its promise-first approach within VIZS: explain what the merchant promises, what retrieved evidence supports or contradicts it, and what to expect. Both Photon messaging and the animated-pet Chrome extension remain core channels sharing one backend. The reference's "browser extension out" cut-list does not override that explicit user decision.

This document specifies upcoming work. Current code still performs seller research and conservative risk policy with labeled unverified links; it does not yet extract structured promises, retrieve domain registration records, match images, detect AI images or produce a promise sheet. No product rename, Next.js rewrite, new deployment or full Kept platform implementation is implied.

## User-visible result

Replace a bare verdict with a compact promise sheet. Each topic distinguishes merchant wording from independent corroboration, conflicting terms and unknowns:

| Topic | Merchant promise to capture | Evidence to seek | Safe interpretation |
|---|---|---|---|
| Shipping origin | Claimed origin or local-business wording | Relevant shipping terms and clear origin disclosure | A local company/address is not proof of a local warehouse or shipment origin |
| Arrival | Processing time, transit range, cutoff, region and exceptions | Current listing and shipping-policy quoted spans | Keep processing and transit separate; do not turn estimates into guarantees |
| Returns | Free returns, window, eligibility | Return destination, payer, fees, exclusions and conditions | State disclosed costs/conditions; unknown return shipping cost stays unknown |
| Domain registration | No promise required | Dated registration lookup with provenance | Domain age is context, not business age or proof of fraud |
| Photo reuse | Implied product depiction | Matched image and source page with provenance | Reuse does not prove dropshipping, counterfeit goods, identical items or shared supplier |
| AI-photo signal | Implied real-item depiction | Optional independently evaluated detector | Secondary, unavailable until validated; never infer it from an LLM's impression |

Every factual line must link to a source actually retrieved for that assessment. Merchant policy retrieval establishes what the merchant wrote, not whether the merchant will perform. Do not copy the brief's example origin, cost, age, price or detector confidence into a real assessment.

## Proposed promise record (D-owned contract work)

Before implementation, define a bounded Pydantic contract containing topic, merchant wording, exact supporting quote, source URL/title, retrieval time, source/content kind, evidence relationship and applicable conditions (region, processing/transit, eligibility, currency). A topic can be supported_as_statement, independently_corroborated, conflicting, not_disclosed, or unavailable. These are proposed categories, not existing API fields. A statement can be supported as merchant wording while fulfillment remains unknown.

An extracted quote must be a real span of retrieved content, not text invented by the model or inferred from a URL. Search snippets remain explicitly snippets; do not label them captured page policy. Conflicting claims need both source records and quotes. Keep request identity, call limits and final interpretation backend-controlled. Grok extracts bounded structured data; Python validates spans and applies wording/rules.

Unknown and unavailable must remain different: not_disclosed means the inspected sources omitted the information, unavailable means the source/check could not be obtained. Do not claim the whole site has no policy after inspecting only search snippets.

## Deterministic response rules

- Lead with "what to expect" and verification actions. Never accuse a merchant of being a scam.
- Compare claims only for matching seller, product context, region and policy conditions. A shop's self-asserted authorization is not manufacturer corroboration.
- No numerical fraud/authenticity probability. The brief's AI-photo confidence ranges are not authorized output without calibrated held-out validation.
- Costs require disclosed amounts or an explicitly explained external estimate with currency, route/assumptions and timestamp. No invented return-shipping estimate or matched-item price.
- Retain LOWER_RISK/HIGHER_RISK/INSUFFICIENT_EVIDENCE and existing decision rules internally during migration. New context signals alone do not upgrade or downgrade risk. Changing public categories requires explicit contract/UI tests.
- If nothing is corroborated, present specific unknowns and available references instead of only "insufficient evidence". Research errors are not adverse merchant evidence.

## Channel behavior

Photon reply: concise highest-impact promise/condition, key unknown, next action and up to two intact labeled links. Avoid unsupported arrival dates, guarantees and implied legal conclusions.

Extension: the pet animates while the request is pending; its panel shows structured promise/evidence rows and expandable quoted sources. Reviewing-source animation requires actual backend phase information. Render returned text safely. No browsing-history collection or payment-field scraping.

Both channels use the same structured assessment/policy. The pet extension does not need Codex or ChatGPT Work Pets APIs. Existing page/SMS content is untrusted data; provider keys remain server-side.

## Implementation sequence and named ownership

1. D: app/models/ and docs/API_CONTRACTS.md define promise/topic/source-span records and backwards-compatible assessment fields. tests/test_contracts.py and labeled tests/fixtures/ cover supported, conflicting, absent, unavailable and conditional statements.
2. C: app/research/, app/services/tavily.py and tests/test_research.py retain source-kind provenance and retrieve relevant listing/shipping/return content with strict bounds and safety. Decide explicit allowlisted retrieval/provider access before any page fetch. Existing URL syntax/DNS checks are not connection-time/redirect-safe direct fetching.
3. B: app/services/grok.py, app/agents/ and tests/test_grok.py extract promise records through validated JSON; reject invented spans and unsupported tasks. Request schema/dependency changes from owners rather than duplicating models.
4. D/A: app/decision/, app/workflow/, app/api/ and owned tests format useful promise-first results while preserving uncertainty, old client compatibility and Photon source links.
5. C: add domain registration lookup as context using verified provider documentation and explicit call limits; missing/unsupported data remains unknown. Do not treat a registration date as store age or domain age as fraud.
6. Image matching: later bounded provider integration or clearly labeled fixture, with image/page URLs and provenance. Perceptual similarity is evidence of similarity, not common origin. AI-photo detection remains deferred until actual model access and evaluation justify its output.
7. Frontend owner (still unassigned): extension/ renders promise rows and honest pet states against fixtures, then the shared backend. A maintains the reproducible Photon test path. No additional agents launched by this specification.

First acceptance target: a synthetic store's "free returns" claim and policy showing customer-paid returns produce a cited, conditional conflict explanation in both channel formats, without a scam label or invented cost. An absent policy and provider failure must produce different states. Add tests for injection, unrelated sellers/regions, stale/contradictory terms, missing quotes, model-invented spans and duplicated snippets. No live paid calls are needed to build these fixture tests.

## Not adopted from the broader brief

This credibility request does not authorize autonomous payments, Visa Acceptance/Microform/TAP, card handling, payment-bound receipts, RFC 3161 timestamp integration, post-purchase tracking, dispute/legal advice or auto-filing, public merchant reputation, GPU data generation/fine-tuning, a 300-store study, mass scraping, new product categories, or a new application stack. These need separate scope, access and validation. A simple retrieval timestamp is not an independent certified timestamp or immutable historical snapshot.

The supplied FTC/Visa statistics, competitor comparisons, model capabilities/licenses, timing estimates and legal/dispute table are source material, not verified repository facts. Before publishing any such claim, verify the primary source and date. No bank outcome, return right or dispute deadline should be asserted from this brief alone. The referenced docs/RESEARCH.md and CLUADE.md are external reference names, not instructions to fabricate missing repository files. Human story/screenshot collection requires consent and is not performed by this update.

## Current status and handoff

Documentation-only specification added in the A integration checkout. Current implemented proof remains the f5af5ba backend and user-confirmed iMessage cited response (five Tavily records, two retained, three filtered). Last code checks were 116 Python/four bridge tests; no new code test, paid request, message, deployment, commit or push is claimed for this specification. First next task is D's bounded promise contract and labeled fixtures, coordinated with C/B/A; preserve existing APIs and both channels.
