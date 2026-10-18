# Project brief — AI-powered shopping decision assistant

**Source:** team-supplied Cursor project plan, adapted for a hackathon P0. **Status:** concept and proposed contracts, **not confirmed implementation**.

## Customer and problem

Shoppers buying fragrances online cannot easily distinguish reliable sellers, legitimate gray-market listings, unusual discounts, and unproven counterfeit allegations. They also have trouble comparing rewards among cards they already own.

**Core proposition:** "Before you buy, know whether the seller is trustworthy, whether the price is reasonable, and which credit card gives you the best value."

## One-minute demo

1. User sends a sample fragrance listing URL by **real SMS** to the team agent's Photon 2.0 messaging channel.
2. FastAPI receives a verified Photon event and processes it; Grok extracts the URL and research objectives.
3. A single research provider retrieves available seller evidence and its URLs. Python validates claim/source relationships and risk policy.
4. Photon sends back a short SMS: classification, buying advice, one or two grounded evidence links, and honest uncertainty.
5. Show one negative example (`INSUFFICIENT_EVIDENCE`) rather than a fabricated certainty. A simulation is acceptable for development but **not evidence of a live Photon integration**.

## P0 — demo-critical

- [ ] Live inbound and outbound Photon 2.0 message (subject to verified access and beta capability)
- [ ] Functional FastAPI and local `/api/v1/evaluate` path
- [ ] Grok structured extraction (or clear fallback if blocked)
- [ ] One search provider with traceable source URLs
- [ ] Source validation and conservative deterministic decision rules
- [ ] Concise response, error and timeout behavior

## P1 — after P0 success

- [ ] Compare identical fragrance sizes/concentrations/editions and date/merchant-specific prices
- [ ] Optimize rewards across manually provided card names and known rules using deterministic arithmetic
- [ ] SMS DETAILS follow-up for richer sources
- [ ] Optional parallel tools, persistence, or hosted dashboard if genuinely needed

## P2 — not before deadline

Multiple deployed autonomous agents, real user account/banking connections, automated checkout, Visa TAP, historical calibrated fraud probability, generalized product categories, large scraped datasets.

## Correctness commitments

- `LOWER_RISK` ≠ verified genuine; `HIGHER_RISK` ≠ legally established scam; `INSUFFICIENT_EVIDENCE` means we cannot conclude.
- Manufacturer authorization is a distinct verifiable question from authenticity; gray-market goods may be authentic.
- Treat public complaints/reviews as allegations unless independently established.
- No invented evidence URLs or numeric probability, no PAN/CVV/banking passwords via SMS.

## Unresolved human decisions

- [ ] Confirm team roster/owners and live Photon 2.0 beta access
- [ ] Confirm working Grok credentials and supported structured-output model
- [ ] Choose Tavily vs native Grok Web Search (not both for first integration)
- [ ] Hosting/public HTTPS decision and working deployment
- [ ] Whether card comparison makes the final demo; do not let it threaten P0
