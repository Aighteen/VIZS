# Devpost draft (final due Sun Oct 18, 10:00 AM PDT)

Copy into Devpost and edit. Everything below matches what was run on Oct 17-18; do not add claims
that were not run. Fields marked `TBD` are for the team.

## Title

VIZS: Who am I really buying from?

## Tagline (one line)

A shopping pet and an iMessage agent that check the seller behind a product link and quote the store's own promises, with sources, before you pay.

## Inspiration

Shopping online means trusting a seller you can't see. Ad links lead to lookalike stores, marketplaces hide who ships the item, and return terms live in legal pages that nobody reads. We wanted a second opinion that shows its evidence and says "I don't know" when it doesn't.

## What it does

Send a product link. You can click the pet on the page in Chrome, or text the link over iMessage. VIZS replies with:

- **A seller assessment:** LOWER_RISK, INSUFFICIENT_EVIDENCE or HIGHER_RISK, with a plain action: consider buying, verify first, or avoid.
- **Brand-direct detection.** If an independent reference source (Wikipedia, Wikidata or Britannica) names the exact domain as the brand's official site, VIZS says you are on the brand's own store. Lookalike domains, marketplaces, multi-brand retailers and a store's claims about itself never qualify.
- **The merchant's own promises:** shipping, processing time, transit time, returns and return cost. Each one is quoted word for word from the store's pages and linked, and labelled "fulfillment unverified". If the pages don't say, VIZS says "not disclosed" or "check unavailable" rather than guessing.
- **Unverified links** to every source it used.

An unknown seller is not called a fraud, and a low price is not called a counterfeit.

## How we built it

- **Two channels, one backend.** A Chrome MV3 extension with an animated on-page pet (user-triggered, paired with a token) and a Photon Spectrum SDK iMessage bridge both call one FastAPI backend.
- **Grok (xAI)** handles two narrow extraction jobs with strict JSON schemas: (1) turning the user's message into a plan (URL, price, brand), and (2) reading the merchant's policy text into promise rows that each carry exact quotes. A fast non-reasoning model is used for the second job.
- **Tavily** runs a fixed seller search, extracts up to 3 pages from the seller's own site and, for brand-direct checks, reads one reference page.
- **RDAP** gives domain registration context.
- **Python makes every decision.** It checks that each quote is an exact, whole-word, on-topic span of the retrieved page. It rejects negated quotes ("returns" taken from "No returns." is dropped), FAQ questions and invented text, and applies a fixed risk policy. Grok's own wording never decides a verdict.
- **Safety and privacy:**
  - URL safety: public destinations only, ad-tracking parameters stripped, provider-substituted pages rejected.
  - Diagnostics use fixed wording only, never page text or URLs.
  - No provider calls at startup.
  - About 925 offline Python tests plus 79 extension and 38 iMessage-bridge tests.

## Challenges

- **The live run first returned nothing.** Ad-tracking parameters (gclid, gbraid, gad_*) made Tavily respell the listing URL, and the exact-match check threw the page away. Then the promise reader timed out on long legal pages. We fixed both: matching on the exact host and path, and sending only policy lines to a faster model.
- **A brand's own store could never be called low risk,** because a store vouching for itself must not count. We added a brand-direct rule that relies on independent reference sources. Live calibration caught a multi-brand retailer (Bluemercury) passing, so the rule now also requires the reference to describe a brand, not a retailer.

## Accomplishments

- A real iMessage run on a Le Labo product link with ad-tracking parameters (the backend check takes about 16 s). The reply was LOWER_RISK (brand's own store, Wikipedia cited) with the store's shipping and returns terms quoted.
- Negatives stay cautious live: an Amazon listing, a multi-brand beauty retailer, an authorized multi-brand reseller and an Apple partner store all stayed "verify first".

## What we learned

TBD (team)

## What's next

- A Wikidata official-website lookup so more brands are recognized (Glossier, Patagonia and Aesop are currently missed).
- SMS and a hosted webhook (not built or verified yet).
- Product authenticity, which VIZS does not establish today.

## Built with

Python, FastAPI, Pydantic, httpx, xAI Grok API, Tavily Search and Extract, RDAP, Chrome Extensions (MV3), JavaScript, Photon Spectrum SDK (iMessage), Node.js

## Honest limits (put these in the submission)

- **Channels:** iMessage via the Photon Spectrum SDK is proven. SMS, public hosting and the FastAPI Photon webhook are not.
- **Brand-direct coverage:** it needs a reference source that names the exact domain. Brands without one, regional domains not listed there, and brands Wikipedia calls "retailers" get "verify first".
- **Promises:** quotes show what the store says, not what it does. Some topics are "not disclosed" or "check unavailable".
- **No authenticity check:** VIZS does not verify that a product is authentic.
- **Provider errors:** occasional transient xAI errors make a check "unavailable"; resending works.

## Sample inputs and the two cases

1. **Credible:** `https://www.lelabofragrances.com/santal-33-147.html` (with or without ad parameters). Result: LOWER_RISK / consider buying, brand's own store, Wikipedia reference, quoted return and transit terms.
2. **Insufficient evidence:** a marketplace listing of the same product (Amazon) or a multi-brand retailer. Result: INSUFFICIENT_EVIDENCE / verify first, with sources.

## Tracks (team decides; see docs/TRACK_DECISION.md)

- Title: VISA: Reimagine Shopping (TBD: team approval)
- Photon Messaging Agent: real iMessage via Spectrum SDK, recorded in the video (TBD: team approval)

## Team contributions

TBD

---

## 90-second video script

| Time | Show | Say |
|---|---|---|
| 0-10 s | An ad link to a perfume store; a lookalike store next to it | "Ad links, lookalike stores, return terms buried in legal pages. Who are you really buying from?" |
| 10-30 s | Phone: text the Le Labo link (with ad parameters) to the Photon iMessage number; reply arrives | "Text VIZS a product link over iMessage, built on Photon's Spectrum SDK." |
| 30-50 s | Read the reply: LOWER_RISK, "Brand's own store", Wikipedia link, quoted return terms | "It found an independent source naming this domain as Le Labo's official site, and it quotes the store's own return terms, word for word, with links." |
| 50-65 s | Chrome: the pet on a marketplace or retailer listing, click Check seller, panel says Verify first | "On a marketplace listing it stays cautious: verify first, with its sources. No made-up fraud claims." |
| 65-80 s | Quick diagram: Grok extracts, Tavily retrieves, Python validates quotes and decides | "Grok only extracts. Python checks that every quote is really on the page, and a fixed policy makes the call." |
| 80-90 s | Limits slide | "It doesn't prove a product is authentic, and brands without a reference source get 'verify first'. Next: Wikidata lookup and SMS." |

Recording tips: one bounded iMessage run evaluates one URL, so start a new `npm run shop -- --live` for each take. If a reply says "extraction is unavailable", it is the intermittent xAI error; restart and resend.
