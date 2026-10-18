"""End-to-end acceptance suite: a credible brand selling on its own store.

All data here is SYNTHETIC. Page texts and search snippets are short invented
sentences shaped like real provider output (no copied page content); live
calibration notes are in tests/qa_fixtures/brand_store_live_notes.md. Nothing
here is live research or sponsor usage, and no test touches the network.

What runs
---------
``evaluate(scenario)`` assembles the real ``app.workflow.runtime.runtime_workflow``
(real Grok extractor, Tavily adapter, seller research, promise pipeline, RDAP
lookup, policy) with every outbound request answered by ``httpx.MockTransport``,
then produces the reply through ``app.api.routes.run_message_evaluation``, the
same function behind POST /api/v1/evaluate-message, so ``message_text`` is the
exact user-facing reply.

Reusable fixture builders (import them from this module)
--------------------------------------------------------
- ``Scenario``: one evaluation. Fields: ``listing`` (URL the user sends),
  ``pages`` ({url: text} the fake Tavily Extract can return), ``search``
  (Tavily Search result items, or a callable ``query -> items``), ``promise``
  (xAI promise reply; see below), ``plan`` (xAI plan reply; default echoes the
  user's URL like a well-behaved model), ``rdap`` (payload or Response) and
  ``extract`` (override for Tavily Extract: callable ``request -> Response``).
  After ``evaluate`` it records ``calls``, ``search_queries``, ``extract_urls``.
- ``tavily_hit(url, title, content)``: one Tavily Search result item.
- ``tavily_search_response(query, items)`` / ``tavily_extract_response(...)``:
  provider-shaped JSON bodies (request_id, response_time, failed_results ...).
- ``xai_chat(content, finish_reason=...)``: xAI chat.completion body.
- ``xai_error(status)``: xAI-style HTTP error response.
- ``faithful_promises([(topic, quote), ...])``: an xAI promise reply that
  behaves like a careful model: it reads the source registry Grok was sent and
  cites the source_id whose content contains each quote (skipping quotes that
  appear nowhere). ``raw_promises(rows)`` returns rows verbatim (for invented
  quotes or invented source ids).
- ``raise_exc(exc)``: a handler that raises (timeouts, connection errors).
- ``reply_text`` and ``assert_*`` helpers state the end goal and safety rules.

Expected outcomes
-----------------
End-goal positives (``END_GOAL`` xfail, non-strict, lanes A/B/C implement them):
for a brand's own store that at least two independent sources (different
registrable domains, none of them the seller's) name as the official store,
the reply must not say "Verify authorization", and every promise topic the
page states must not read "check unavailable".
Every negative/safety case is a normal test that passes on current code and
must keep passing after the brand-direct change: lookalike domains,
marketplaces, self-asserted "official" claims, a single forum source,
independent sources naming a different official domain, invented model
quotes, substituted extract pages and xAI timeout/HTTP 400/truncation.
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

import httpx
import pytest

from app.api.routes import run_message_evaluation
from app.config import Settings
from app.decision import decide, format_sms
from app.decision.rules import registrable_domain
from app.models import Decision, Risk
from app.research.url_safety import public_url
from app.services.grok import _provided_urls
from app.workflow.runtime import runtime_workflow

NOW_EPOCH = 1792238400  # 2026-10-17T12:00:00Z, fixed for provider-shaped bodies
XAI_KEY = "qa-synthetic-xai-key-do-not-use"
TAVILY_KEY = "qa-synthetic-tavily-key-do-not-use"
END_GOAL = pytest.mark.xfail(strict=False, reason="end goal: lanes A/B/C")
TOPICS = ("shipping_origin", "processing_time", "transit_time", "returns", "return_cost")

# Output must never accuse, claim certainty, or give probabilities (AGENTS.md).
BANNED = [r"\d+(?:\.\d+)?\s*%", r"\bpercent\b", r"\bprobabilit", r"\bscam", r"\bcounterfeit",
          r"\bfake\b", r"\bfraudulent\b", r"\b(?:is|are) (?:a )?fraud\b", r"\bguarantee",
          r"\bauthentic(?:ity)? (?:is )?(?:verified|confirmed|guaranteed)\b"]


# ------------------------------------------------------------------ provider shapes

def tavily_hit(url, title, content, score=0.71):
    """One Tavily Search result item (include_raw_content=False => raw_content null)."""
    return {"url": url, "title": title, "content": content, "score": score, "raw_content": None}


def tavily_search_response(query, items):
    return {"query": query, "follow_up_questions": None, "answer": None, "images": [],
            "results": items, "response_time": "1.12", "request_id": "synthetic-search"}


def tavily_extract_response(results, failed=()):
    return {"results": [{"url": u, "raw_content": t, "images": []} for u, t in results],
            "failed_results": [{"url": u, "error": "Failed to fetch url"} for u in failed],
            "response_time": 2.31, "request_id": "synthetic-extract"}


def xai_chat(content, finish_reason="stop", **message):
    """xAI /v1/chat/completions body (non-streaming)."""
    if not isinstance(content, str):
        content = json.dumps(content)
    return httpx.Response(200, json={
        "id": "synthetic-completion", "object": "chat.completion", "created": NOW_EPOCH,
        "model": "qa-synthetic-model", "system_fingerprint": "fp_synthetic",
        "choices": [{"index": 0, "finish_reason": finish_reason,
                     "message": {"role": "assistant", "content": content, "refusal": None, **message}}],
        "usage": {"prompt_tokens": 1800, "completion_tokens": 400, "total_tokens": 2200}})


def xai_error(status=400, message="Invalid request content"):
    return httpx.Response(status, json={"code": "Client specified an invalid argument", "error": message})


def raise_exc(exc):
    def handler(request):
        raise exc
    return handler


def promise_row(topic, quotes, status="supported_as_statement", statement=None,
                explanation="Model wording (not authoritative).", **conditions):
    return {"topic": topic, "status": status, "merchant_statement": statement, "explanation": explanation,
            "quotes": [{"source_id": s, "quote": q} for s, q in quotes], "conditions": conditions}


def faithful_promises(specs):
    """xAI promise reply from a careful model: cites the registry source that holds each quote."""
    def handler(request):
        sources = json.loads(json.loads(request.content)["messages"][1]["content"])["sources"]
        rows = []
        for topic, quote in specs:
            source = next((s for s in sources if s["content_kind"] == "merchant_page" and quote in s["content"]), None)
            if source:
                rows.append(promise_row(topic, [(source["source_id"], quote)], statement=quote))
        return xai_chat({"records": rows})
    return handler


def raw_promises(rows):
    return lambda request: xai_chat({"records": rows})


def _page_key(url):
    parts = urlsplit(public_url(url))
    return parts.hostname.removeprefix("www."), unquote(parts.path).rstrip("/") or "/"


@dataclass
class Scenario:
    listing: str
    pages: dict = field(default_factory=dict)
    search: Any = field(default_factory=list)
    promise: Any = None
    plan: Any = None
    extract: Callable | None = None
    rdap: Any = None
    message: str | None = None
    calls: list = field(default_factory=list)
    search_queries: list = field(default_factory=list)
    extract_urls: list = field(default_factory=list)

    # Tavily Extract: pages are matched by host+path and echoed under the requested
    # URL; ``canonical=True`` answers with the page's own (query-less) URL instead.
    canonical: bool = False

    def _extract(self, request):
        urls = json.loads(request.content)["urls"]
        self.extract_urls.extend(urls)
        if self.extract is not None:
            return self.extract(request)
        pages = {_page_key(u): (u, t) for u, t in self.pages.items()}
        found = [(pages[_page_key(u)][0] if self.canonical else u, pages[_page_key(u)][1])
                 for u in urls if _page_key(u) in pages]
        failed = [u for u in urls if _page_key(u) not in pages]
        return httpx.Response(200, json=tavily_extract_response(found, failed))

    def _plan(self, request):
        if self.plan is not None:
            return self.plan(request) if callable(self.plan) else self.plan
        message = json.loads(request.content)["messages"][1]["content"]
        (url,) = _provided_urls(message)
        return xai_chat({"request_id": "backend", "intent": "evaluate_purchase", "product_url": url,
                         "tasks": [{"kind": "verify_seller", "query": "model query"}]})

    def handler(self, request):
        host, path = request.url.host, request.url.path
        if host == "api.x.ai":
            name = json.loads(request.content)["response_format"]["json_schema"]["name"]
            self.calls.append(name)
            if name == "shopping_plan":
                return self._plan(request)
            spec = self.promise if self.promise is not None else raw_promises([])
            return spec(request) if callable(spec) else spec
        if host == "api.tavily.com":
            self.calls.append(path)
            if path == "/extract":
                return self._extract(request)
            query = json.loads(request.content)["query"]
            self.search_queries.append(query)
            items = self.search(query) if callable(self.search) else self.search
            return httpx.Response(200, json=tavily_search_response(query, items))
        if host == "rdap.verisign.com":
            self.calls.append("rdap")
            if isinstance(self.rdap, httpx.Response):
                return self.rdap
            domain = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=self.rdap or {
                "objectClassName": "domain", "ldhName": domain.upper(),
                "events": [{"eventAction": "registration", "eventDate": "2006-03-14T18:20:11Z"},
                           {"eventAction": "expiration", "eventDate": "2027-03-14T18:20:11Z"}]})
        raise AssertionError(f"Unexpected outbound host: {host}")


def live_settings(**changes):
    return Settings(**{"provider_mode": "live", "xai_api_key": XAI_KEY, "xai_model": "qa-synthetic-model",
                       "tavily_api_key": TAVILY_KEY, **changes})


async def _stub_destination(url):
    # Stub destination validator: syntax/scheme checks only, no DNS.
    return public_url(url)


async def _evaluate(scenario, settings):
    transport = httpx.MockTransport(scenario.handler)
    async with runtime_workflow(settings, xai_transport=transport, tavily_transport=transport,
                                domain_transport=transport, destination_validator=_stub_destination) as workflow:
        body = json.dumps({"request_id": "brand-store-qa", "channel": "debug",
                           "message_text": scenario.message or f"Check this listing <{scenario.listing}>"}).encode()

        async def stream():
            yield body
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            workflow=workflow, settings=settings, format_sms=format_sms)), headers={}, stream=stream)
        return await run_message_evaluation(request)


def evaluate(scenario, settings=None):
    """Run one evaluation; returns (assessment, message_text) exactly as /api/v1/evaluate-message."""
    out = asyncio.run(_evaluate(scenario, settings or live_settings()))
    return out["assessment"], out["message_text"]


# ------------------------------------------------------------------ end goal / safety checks

def reply_text(scenario):
    return evaluate(scenario)[1]


def assert_no_accusation(text):
    for pattern in BANNED:
        assert not re.search(pattern, text, re.IGNORECASE), f"banned wording {pattern!r} in: {text}"


def assert_quotes_are_spans(assessment, scenario):
    """Every quoted promise is an exact span of a page Tavily returned for the seller."""
    seller = urlsplit(scenario.listing).hostname.removeprefix("www.")
    sheet = assessment.promise_sheet
    registry = {s.source_id: s for s in sheet.sources}
    pages = {_page_key(u): t for u, t in scenario.pages.items()}
    for row in sheet.records:
        for quote in row.quotes:
            source = registry[quote.source_id]
            assert quote.quote in source.content
            if source.content_kind == "merchant_page":
                assert source.url.host.removeprefix("www.") == seller
                assert quote.quote in pages[_page_key(str(source.url))]


def assert_not_brand_direct(assessment, text):
    """Safety: the listing is not treated as the brand's own store."""
    assert assessment.seller_risk != "LOWER_RISK"
    assert assessment.decision == "VERIFY_FIRST"
    assert "Verify authorization" in text
    assert "Product authenticity is not established." in text
    assert_no_accusation(text)


def assert_stated_topics_shown(assessment, text, stated):
    rows = {r.topic: r for r in assessment.promise_sheet.records}
    for topic in stated:
        assert rows[topic].status != "unavailable", (topic, rows[topic].explanation)
        assert f"{topic.replace('_', ' ')}: check unavailable" not in text
    assert "Merchant statement" in text


def assert_unavailable_or_exact(assessment, scenario, text, invented=()):
    """After a failure: rows are honest (unavailable, or exact spans), nothing invented leaks."""
    assert_quotes_are_spans(assessment, scenario)
    for phrase in invented:
        assert phrase not in text
    for row in assessment.promise_sheet.records:
        if row.status == "unavailable":
            assert not re.search(r"https?://|www\.", row.explanation)


# ------------------------------------------------------------------ brand-store fixtures

@dataclass(frozen=True)
class BrandStore:
    """A brand's own store: listing URL, its pages and independent mentions."""
    name: str
    listing: str
    pages: dict
    own_hits: tuple            # search hits hosted on the store itself
    independent: tuple         # >=2 independent hits naming the store as official
    stated: dict               # topic -> exact quote present on a page


LE_LABO = BrandStore(
    name="Le Labo",
    listing=("https://www.lelabofragrances.com/santal-33-147.html?gclid=Cj0KCQjw-synthetic-ZxYwVuTsRqPoNmLk"
             "&gbraid=0AAAAAD-synthetic-gbraid&gad_source=1&gad_campaignid=12345678901"),
    pages={
        "https://www.lelabofragrances.com/santal-33-147.html":
            "Santal 33 eau de parfum 50 ml. Complimentary standard shipping on every order. "
            "Orders are processed within 1-2 business days. Standard delivery takes 3-5 business days. "
            "Orders ship from our New Jersey distribution center.",
        "https://www.lelabofragrances.com/terms-and-conditions-of-sale.html":
            "Terms and Conditions of Sale. These terms govern purchases made on lelabofragrances.com in the "
            "United States.",
        "https://www.lelabofragrances.com/faq-returns.html":
            "Cancellation rights FAQ. Unused products may be returned within 30 days of delivery. "
            "Return shipping is free using the prepaid label included with your order.",
    },
    own_hits=(
        tavily_hit("https://www.lelabofragrances.com/terms-and-conditions-of-sale.html",
                   "Terms & Conditions of Sale | Le Labo",
                   "These terms govern purchases made on lelabofragrances.com in the United States."),
        tavily_hit("https://www.lelabofragrances.com/faq-returns.html", "Cancellation Rights FAQ | Le Labo",
                   "Unused products may be returned within 30 days of delivery."),
    ),
    independent=(
        tavily_hit("https://en.wikipedia.org/wiki/Le_Labo", "Le Labo - Wikipedia",
                   "Le Labo is a perfume house founded in New York in 2006. Website: lelabofragrances.com "
                   "(official online store)"),
        tavily_hit("https://www.fragrantica.com/designers/Le-Labo.html", "Le Labo perfumes and colognes",
                   "Le Labo fragrances are sold at the official Le Labo store, lelabofragrances.com, and at "
                   "authorized department stores."),
    ),
    stated={"shipping_origin": "Orders ship from our New Jersey distribution center.",
            "processing_time": "Orders are processed within 1-2 business days.",
            "transit_time": "Standard delivery takes 3-5 business days.",
            "returns": "Unused products may be returned within 30 days of delivery.",
            "return_cost": "Return shipping is free using the prepaid label included with your order."},
)

AESOP = BrandStore(  # plain .com with a regional path segment
    name="Aesop",
    listing="https://www.aesop.com/us/p/body-hand/hand/resurrection-aromatique-hand-balm/",
    pages={
        "https://www.aesop.com/us/p/body-hand/hand/resurrection-aromatique-hand-balm/":
            "Resurrection Aromatique Hand Balm 75 mL. Orders placed before 1pm ET are dispatched the same "
            "business day. Standard shipping arrives in 4-6 business days.",
        "https://www.aesop.com/us/r/shipping-returns/":
            "Shipping and returns. Orders are dispatched from our warehouse in New York. Unopened products "
            "can be returned within 30 days of purchase. Returns are free of charge for US orders.",
    },
    own_hits=(tavily_hit("https://www.aesop.com/us/r/shipping-returns/", "Shipping & Returns | Aesop United States",
                         "Unopened products can be returned within 30 days of purchase."),),
    independent=(
        tavily_hit("https://en.wikipedia.org/wiki/Aesop_(brand)", "Aesop (brand) - Wikipedia",
                   "Aesop is an Australian cosmetics brand founded in Melbourne in 1987. Official website: "
                   "aesop.com"),
        tavily_hit("https://www.vogue.com/article/aesop-hand-balm-review", "The hand balm editors keep buying",
                   "Buy it directly from the brand's official store at aesop.com or at Aesop signature stores."),
    ),
    stated={"shipping_origin": "Orders are dispatched from our warehouse in New York.",
            "processing_time": "Orders placed before 1pm ET are dispatched the same business day.",
            "transit_time": "Standard shipping arrives in 4-6 business days.",
            "returns": "Unopened products can be returned within 30 days of purchase.",
            "return_cost": "Returns are free of charge for US orders."},
)

WHITTARD = BrandStore(  # regional ccTLD (.co.uk): no RDAP context available, by design
    name="Whittard of Chelsea",
    listing="https://www.whittard.co.uk/tea/loose-leaf-tea/english-breakfast-loose-tea-100g-301451.html",
    pages={
        "https://www.whittard.co.uk/tea/loose-leaf-tea/english-breakfast-loose-tea-100g-301451.html":
            "English Breakfast loose tea 100g. We aim to dispatch orders within 2 working days. "
            "UK standard delivery takes 3-5 working days.",
        "https://www.whittard.co.uk/customer-service/returns.html":
            "Returns. Unopened items can be returned within 28 days for a full refund. Return postage is free "
            "for UK customers using the enclosed returns label. All parcels are dispatched from our warehouse "
            "in Leicestershire.",
    },
    own_hits=(tavily_hit("https://www.whittard.co.uk/customer-service/returns.html", "Returns | Whittard of Chelsea",
                         "Unopened items can be returned within 28 days for a full refund."),),
    independent=(
        tavily_hit("https://en.wikipedia.org/wiki/Whittard_of_Chelsea", "Whittard of Chelsea - Wikipedia",
                   "Whittard of Chelsea is a British tea retailer founded in 1886. Website: whittard.co.uk "
                   "(official store)"),
        tavily_hit("https://www.which.co.uk/news/article/best-tea-gift-sets", "Best tea gift sets - Which?",
                   "Whittard sells its own range through its official online shop, whittard.co.uk, and its high "
                   "street stores."),
    ),
    stated={"shipping_origin": "All parcels are dispatched from our warehouse in Leicestershire.",
            "processing_time": "We aim to dispatch orders within 2 working days.",
            "transit_time": "UK standard delivery takes 3-5 working days.",
            "returns": "Unopened items can be returned within 28 days for a full refund.",
            "return_cost": "Return postage is free for UK customers using the enclosed returns label."},
)

ALLBIRDS = BrandStore(  # Shopify-hosted brand domain (/products/<handle>?variant=...)
    name="Allbirds",
    listing="https://www.allbirds.com/products/mens-wool-runners?variant=40195939811408",
    pages={
        "https://www.allbirds.com/products/mens-wool-runners":
            "Men's Wool Runners. Free shipping on orders over $75. Orders typically ship within 1-2 business "
            "days. Standard delivery takes 3-7 business days after shipment.",
        "https://www.allbirds.com/pages/returns-exchanges":
            "Returns and exchanges. Unworn shoes can be returned within 30 days of delivery. Return shipping is "
            "free for US orders.",
    },
    own_hits=(tavily_hit("https://www.allbirds.com/pages/returns-exchanges", "Returns & Exchanges - Allbirds",
                         "Unworn shoes can be returned within 30 days of delivery."),),
    independent=(
        tavily_hit("https://en.wikipedia.org/wiki/Allbirds", "Allbirds - Wikipedia",
                   "Allbirds, Inc. is a New Zealand-American footwear company founded in 2015. Website: "
                   "allbirds.com (official store)"),
        tavily_hit("https://www.runnersworld.com/gear/a20000000/allbirds-wool-runner-review/",
                   "Allbirds Wool Runner review",
                   "The Wool Runner is sold on the brand's official site, allbirds.com, and in Allbirds stores."),
    ),
    # The page states no shipping origin: that row may honestly stay unavailable.
    stated={"processing_time": "Orders typically ship within 1-2 business days.",
            "transit_time": "Standard delivery takes 3-7 business days after shipment.",
            "returns": "Unworn shoes can be returned within 30 days of delivery.",
            "return_cost": "Return shipping is free for US orders."},
)

BRANDS = [LE_LABO, AESOP, WHITTARD, ALLBIRDS]


def brand_scenario(store: BrandStore, *, independent=None, own_hits=None, promise=None, **changes):
    hits = list(store.own_hits if own_hits is None else own_hits) + list(
        store.independent if independent is None else independent)
    return Scenario(listing=store.listing, pages=dict(store.pages), search=hits[:5],
                    promise=promise or faithful_promises(list(store.stated.items())), **changes)


# ------------------------------------------------------------------ harness self-checks

def test_harness_uses_real_route_providers_and_strips_tracking():
    scenario = brand_scenario(LE_LABO)
    assessment, text = evaluate(scenario)
    assert scenario.calls[:2] == ["shopping_plan", "/search"]
    assert "/extract" in scenario.calls and "promise_records" in scenario.calls and "rdap" in scenario.calls
    # Tavily is never asked for the ad-tracking spelling of the listing.
    assert scenario.extract_urls and not any(re.search(r"gclid|gbraid|gad_", u) for u in scenario.extract_urls)
    assert text == format_sms(assessment)
    assert_quotes_are_spans(assessment, scenario)
    assert_no_accusation(text)


def test_suite_case_runs_fast():
    started = time.monotonic()
    for store in BRANDS:
        evaluate(brand_scenario(store))
    assert time.monotonic() - started < 2


# ------------------------------------------------------------------ positives

@pytest.mark.parametrize("store", BRANDS, ids=lambda s: s.name)
def test_brand_store_promise_rows_show_what_the_page_states(store):
    scenario = brand_scenario(store)
    assessment, text = evaluate(scenario)
    assert_stated_topics_shown(assessment, text, store.stated)
    assert_quotes_are_spans(assessment, scenario)
    assert_no_accusation(text)


@pytest.mark.parametrize("store", BRANDS, ids=lambda s: s.name)  # lane C: was END_GOAL xfail
def test_END_GOAL_brand_store_named_official_by_two_independent_sources(store):
    scenario = brand_scenario(store)
    assessment, text = evaluate(scenario)
    assert "verify authorization" not in text.lower()
    assert assessment.decision != "AVOID" and assessment.seller_risk != "HIGHER_RISK"
    assert "Product authenticity is not established." in text
    assert_stated_topics_shown(assessment, text, store.stated)
    assert_quotes_are_spans(assessment, scenario)
    assert_no_accusation(text)


@pytest.mark.xfail(strict=False, reason="end goal: lanes A/B/C (Shopify ?variant listing, canonical extract URL)")
def test_END_GOAL_extract_answering_with_canonical_url_still_reads_the_listing():
    # Tavily may answer a Shopify ?variant= listing under the canonical product URL.
    scenario = brand_scenario(ALLBIRDS, canonical=True)
    assessment, text = evaluate(scenario)
    assert_stated_topics_shown(assessment, text, ALLBIRDS.stated)
    assert_quotes_are_spans(assessment, scenario)


def test_END_GOAL_official_domain_written_with_www_or_sentence_period():
    # Real snippets often write "www.aesop.com" or end a sentence with the domain.
    independent = (
        tavily_hit("https://en.wikipedia.org/wiki/Aesop_(brand)", "Aesop (brand) - Wikipedia",
                   "Aesop is an Australian cosmetics brand. Official website: www.aesop.com"),
        tavily_hit("https://www.vogue.com/article/aesop-hand-balm-review", "Review",
                   "Buy it from the brand's official online store at https://www.aesop.com/us/."),
    )
    _, text = evaluate(brand_scenario(AESOP, independent=independent))
    assert "verify authorization" not in text.lower()


# ------------------------------------------------------------------ negatives: who the seller is

LE_LABO_OFFICIAL = LE_LABO.independent  # both name lelabofragrances.com as the official store


def lookalike(host, path="/products/santal-33-eau-de-parfum-100ml"):
    listing = f"https://{host}{path}"
    page = (f"Le Labo Santal 33 100ml - official Le Labo store. Orders ship from our warehouse in 2 days. "
            f"Returns accepted within 14 days.")
    own = tavily_hit(f"https://{host}/pages/about", f"About {host}",
                     f"{host} is the official Le Labo outlet store with authentic Le Labo perfume.")
    mention = tavily_hit("https://www.trustpilot.com/review/" + host, f"{host} reviews",
                         f"Reviews of {host}. Customers ask whether {host} is an official Le Labo store.")
    return Scenario(listing=listing, pages={listing: page}, search=[own, mention, *LE_LABO_OFFICIAL],
                    promise=faithful_promises([("returns", "Returns accepted within 14 days.")]))


@pytest.mark.parametrize("host", ["lelabo-outlet-sale.com", "lelabofragrances.co", "le-labo-fragrances.shop",
                                  "lelabofragrances.com.evil.io", "www.lelabofragrances.com-official.shop",
                                  "shop.lelabo-fragrances.com"])
def test_lookalike_domains_are_not_brand_direct(host):
    assessment, text = evaluate(lookalike(host))
    assert_not_brand_direct(assessment, text)
    assert not any(e.claim_status == "verified_fact" for e in assessment.evidence)


@pytest.mark.parametrize("listing", [
    "https://www.amazon.com/Le-Labo-Santal-33-Parfum/dp/B07SYNTH33",
    "https://www.ebay.com/itm/356000000033",
    "https://www.walmart.com/ip/Le-Labo-Santal-33-Eau-de-Parfum-1-7-oz/5000000033",
    "https://www.nordstrom.com/s/le-labo-santal-33-eau-de-parfum/5000033",
])
def test_marketplace_and_reseller_listings_are_not_brand_direct(listing):
    host = urlsplit(listing).hostname.removeprefix("www.")
    # Even two independent sources saying the brand sells "officially" on the marketplace
    # do not make a marketplace listing the brand's own store.
    hits = [tavily_hit(listing, "Le Labo Santal 33", "Visit the Le Labo Store. Ships from and sold by a third party."),
            tavily_hit("https://www.businessoffashion.com/news/le-labo-marketplace", "Le Labo storefront",
                       f"Le Labo now runs an official brand storefront on {host} alongside its own site."),
            tavily_hit("https://www.glossy.co/beauty/le-labo-storefront/", "Brand storefronts",
                       f"The official Le Labo store on {host} lists Santal 33."),
            *LE_LABO_OFFICIAL]
    scenario = Scenario(listing=listing, pages={listing: "Visit the Le Labo Store. Ships from Amazon fulfillment."},
                        search=hits[:5])
    assessment, text = evaluate(scenario)
    assert_not_brand_direct(assessment, text)


def test_seller_own_official_claims_only_unknown_shop():
    listing = "https://www.maison-santal-paris.com/products/santal-33"
    hits = [tavily_hit("https://www.maison-santal-paris.com/pages/authorized-retailer", "Authorized retailer",
                       "maison-santal-paris.com is an official authorized Le Labo retailer."),
            tavily_hit("https://blog.maison-santal-paris.com/official", "Our partnership",
                       "We are the official Le Labo store for Europe: maison-santal-paris.com"),
            tavily_hit("https://shop.maison-santal-paris.com/about", "About",
                       "Official Le Labo distributor maison-santal-paris.com")]
    scenario = Scenario(listing=listing, pages={listing: "Official Le Labo store. 100% authentic."}, search=hits)
    assessment, text = evaluate(scenario)
    assert_not_brand_direct(assessment, text)
    assert "100% authentic" not in text


def test_brand_domain_with_only_its_own_official_claims_stays_verify_first():
    own = [*LE_LABO.own_hits,
           tavily_hit("https://www.lelabofragrances.com/about-us.html", "About Le Labo",
                      "lelabofragrances.com is the official Le Labo online store."),
           tavily_hit("https://stores.lelabofragrances.com/", "Store locator",
                      "Official Le Labo boutiques and lelabofragrances.com")]
    assessment, text = evaluate(brand_scenario(LE_LABO, own_hits=own, independent=()))
    assert_not_brand_direct(assessment, text)


def test_single_forum_source_is_not_enough():
    forum = (tavily_hit("https://www.reddit.com/r/fragrance/comments/abc123/is_lelabofragrancescom_legit/",
                        "Is lelabofragrances.com legit?",
                        "Yes, lelabofragrances.com is Le Labo's official site, ordered there twice."),)
    assessment, text = evaluate(brand_scenario(LE_LABO, independent=forum))
    assert_not_brand_direct(assessment, text)


def test_two_threads_on_one_forum_are_one_source():
    forum = (tavily_hit("https://www.reddit.com/r/fragrance/comments/abc123/thread_one/", "Thread one",
                        "lelabofragrances.com is the official Le Labo store."),
             tavily_hit("https://old.reddit.com/r/Colognes/comments/def456/thread_two/", "Thread two",
                        "Ordered from lelabofragrances.com, the official store, no issues."))
    assessment, text = evaluate(brand_scenario(LE_LABO, independent=forum))
    assert_not_brand_direct(assessment, text)


def test_independent_sources_name_a_different_official_domain():
    listing = "https://le-labo-official.com/santal-33-147.html"
    hits = [tavily_hit("https://en.wikipedia.org/wiki/Le_Labo", "Le Labo - Wikipedia",
                       "Le Labo's official store is lelabofragrances.com; le-labo-official.com is not listed "
                       "as an official site."),
            tavily_hit("https://www.fragrantica.com/news/le-labo-official-sites.html", "Official Le Labo sites",
                       "The official Le Labo website is lelabofragrances.com, not le-labo-official.com "
                       "(reported to the brand).")]
    scenario = Scenario(listing=listing, pages={listing: "Santal 33. Official store. Free returns."}, search=hits)
    assessment, text = evaluate(scenario)
    assert_not_brand_direct(assessment, text)


def test_unknown_seller_with_low_price_is_not_called_fraudulent():
    listing = "https://small-candle-co.com/products/santal-candle"
    scenario = Scenario(listing=listing, pages={listing: "Santal candle 8 oz. Ships in 5 days."},
                        message=f"Check this listing <{listing}> price $12")
    assessment, text = evaluate(scenario)
    assert assessment.decision == "VERIFY_FIRST" and assessment.seller_risk == "INSUFFICIENT_EVIDENCE"
    assert_no_accusation(text)


# ------------------------------------------------------------------ negatives: promise pipeline

def test_invented_grok_quotes_and_source_ids_are_dropped():
    invented = [promise_row("returns", [("source_1", "Free returns within 365 days, no questions asked.")],
                            statement="Free returns within 365 days, no questions asked."),
                promise_row("return_cost", [("source_9", "Return shipping is free using the prepaid label "
                                                         "included with your order.")]),
                promise_row("shipping_origin", [("source_1", "Orders ship from our Paris atelier.")]),
                promise_row("processing_time", [("source_1", "Orders are processed within 1-2 business days.")],
                            time="same day")]
    scenario = brand_scenario(LE_LABO, promise=raw_promises(invented))
    assessment, text = evaluate(scenario)
    assert_unavailable_or_exact(assessment, scenario, text,
                                invented=["365 days", "Paris atelier", "same day"])
    assert {r.topic for r in assessment.promise_sheet.records if r.quotes} <= {"return_cost"}
    assert all(q.source_id != "source_9" for r in assessment.promise_sheet.records for q in r.quotes)


def test_mixed_valid_and_invented_quotes_keep_only_the_valid_row():
    rows_spec = faithful_promises([("transit_time", "Standard delivery takes 3-5 business days.")])

    def handler(request):
        rows = json.loads(rows_spec(request).json()["choices"][0]["message"]["content"])["records"]
        rows.append(promise_row("returns", [("source_1", "Lifetime returns on all fragrances.")]))
        return xai_chat({"records": rows})
    scenario = brand_scenario(LE_LABO, promise=handler)
    assessment, text = evaluate(scenario)
    assert "Standard delivery takes 3-5 business days." in text
    assert_unavailable_or_exact(assessment, scenario, text, invented=["Lifetime returns"])


@pytest.mark.parametrize("substitute", ["https://www.lelabofragrances.com.au/santal-33-147.html",
                                        "https://www.lelabofragrances.com/gift-cards.html",
                                        "https://lelabo-outlet-sale.com/santal-33-147.html"])
def test_tavily_returning_a_different_host_or_path_is_not_quoted(substitute):
    def extract(request):
        return httpx.Response(200, json=tavily_extract_response(
            [(substitute, "SUBSTITUTE PAGE. Returns accepted within 365 days.")],
            failed=json.loads(request.content)["urls"]))
    scenario = brand_scenario(LE_LABO, extract=extract,
                              promise=faithful_promises([("returns", "Returns accepted within 365 days.")]))
    assessment, text = evaluate(scenario)
    assert "365 days" not in text and "SUBSTITUTE" not in text
    assert all(r.status == "unavailable" for r in assessment.promise_sheet.records if r.topic in TOPICS)
    assert not any(str(s.url).startswith(substitute) for s in assessment.promise_sheet.sources)


XAI_FAILURES = {
    "timeout": raise_exc(httpx.ReadTimeout("synthetic read timeout")),
    "connect_error": raise_exc(httpx.ConnectError("synthetic connect error")),
    "http_400": lambda request: xai_error(400, "Invalid response_format schema"),
    "http_429": lambda request: xai_error(429, "Rate limited"),
    "truncated_length": lambda request: xai_chat('{"records": [{"topic": "returns", "status": "supp',
                                                 finish_reason="length"),
    "truncated_json_stop": lambda request: xai_chat('{"records": [{"topic": "returns", "status": "supp'),
    "refusal": lambda request: xai_chat("", refusal="I can't help with that."),
}


@pytest.mark.parametrize("failure", XAI_FAILURES, ids=list(XAI_FAILURES))
def test_xai_promise_call_failures_stay_honest(failure):
    scenario = brand_scenario(LE_LABO, promise=XAI_FAILURES[failure])
    assessment, text = evaluate(scenario)
    assert scenario.calls.count("promise_records") >= 1
    assert assessment.decision != "AVOID" and assessment.seller_risk != "HIGHER_RISK"
    assert_unavailable_or_exact(assessment, scenario, text, invented=["supp"])
    assert_no_accusation(text)


@pytest.mark.parametrize("failure", XAI_FAILURES, ids=list(XAI_FAILURES))
def test_xai_plan_call_failures_do_not_research_or_conclude(failure):
    scenario = brand_scenario(LE_LABO, plan=XAI_FAILURES[failure])
    assessment, text = evaluate(scenario)
    assert assessment.decision == "NEED_MORE_INFORMATION"
    assert "could not be completed" in text
    assert "Send the product listing URL" not in text  # the user already sent it (Q2)
    assert "/search" not in scenario.calls and "promise_records" not in scenario.calls
    assert_no_accusation(text)


def test_rdap_unavailable_does_not_change_the_seller_decision():
    with_rdap, _ = evaluate(brand_scenario(AESOP))
    without, text = evaluate(brand_scenario(AESOP, rdap=httpx.Response(503)))
    assert without.decision == with_rdap.decision and without.seller_risk == with_rdap.seller_risk
    assert without.promise_sheet.domain_context.status == "unavailable"
    assert_no_accusation(text)


# ------------------------------------------------------------------ suite sensitivity (mutation checks)
# Each naive brand-direct rule below is patched into the runtime in place of
# decide(); the named negative case must then fail its safety assertion. This
# shows the negatives catch the rule, not merely that current code is strict.

def _brand_direct(assessment):
    return assessment.model_copy(update={"seller_risk": Risk.LOWER_RISK, "decision": Decision.CONSIDER_BUYING,
                                         "summary": "Brand's own store."})


def naive_brand_name_in_host(request, plan, evidence, promise_sheet=None):
    """Naive rule: any domain containing the brand name is the brand's own store."""
    result = decide(request, plan, evidence, promise_sheet=promise_sheet)
    return _brand_direct(result) if "lelabo" in re.sub(r"[-.]", "", plan.product_url.host) else result


def naive_two_sources_say_official(request, plan, evidence, promise_sheet=None):
    """Naive rule: >=2 non-seller registrable domains mention the seller domain with 'official'."""
    result = decide(request, plan, evidence, promise_sheet=promise_sheet)
    seller = registrable_domain(plan.product_url.host)
    sites = {registrable_domain(e.source_url.host) for e in evidence
             if "official" in (e.excerpt or "").lower() and registrable_domain(e.source_url.host) != seller}
    return _brand_direct(result) if len(sites) >= 2 else result


def naive_two_hosts_say_official(request, plan, evidence, promise_sheet=None):
    """Naive rule: like above, but counts hosts, so two subdomains of one forum look independent."""
    result = decide(request, plan, evidence, promise_sheet=promise_sheet)
    seller = registrable_domain(plan.product_url.host)
    hosts = {e.source_url.host for e in evidence
             if "official" in (e.excerpt or "").lower() and registrable_domain(e.source_url.host) != seller}
    return _brand_direct(result) if len(hosts) >= 2 else result


def naive_trust_official_claims(request, plan, evidence, promise_sheet=None):
    """Naive rule: any retrieved text (including the seller's own) calling it 'official'."""
    result = decide(request, plan, evidence, promise_sheet=promise_sheet)
    return _brand_direct(result) if any("official" in (e.excerpt or "").lower() for e in evidence) else result


def naive_one_independent_source(request, plan, evidence, promise_sheet=None):
    """Naive rule: one non-seller page calling the domain 'official' is enough."""
    result = decide(request, plan, evidence, promise_sheet=promise_sheet)
    seller = registrable_domain(plan.product_url.host)
    return _brand_direct(result) if any("official" in (e.excerpt or "").lower()
                                        and registrable_domain(e.source_url.host) != seller
                                        for e in evidence) else result


MUTANTS = [
    (naive_brand_name_in_host, "test_lookalike_domains_are_not_brand_direct", {"host": "lelabo-outlet-sale.com"}),
    (naive_brand_name_in_host, "test_lookalike_domains_are_not_brand_direct", {"host": "lelabofragrances.co"}),
    (naive_brand_name_in_host, "test_lookalike_domains_are_not_brand_direct",
     {"host": "lelabofragrances.com.evil.io"}),
    (naive_two_sources_say_official, "test_marketplace_and_reseller_listings_are_not_brand_direct",
     {"listing": "https://www.amazon.com/Le-Labo-Santal-33-Parfum/dp/B07SYNTH33"}),
    (naive_two_sources_say_official, "test_independent_sources_name_a_different_official_domain", {}),
    (naive_two_hosts_say_official, "test_two_threads_on_one_forum_are_one_source", {}),
    (naive_trust_official_claims, "test_seller_own_official_claims_only_unknown_shop", {}),
    (naive_trust_official_claims, "test_brand_domain_with_only_its_own_official_claims_stays_verify_first", {}),
    (naive_one_independent_source, "test_single_forum_source_is_not_enough", {}),
]


@pytest.mark.parametrize("mutant,case,kwargs", MUTANTS, ids=[f"{m.__name__}-{c[5:]}" for m, c, _ in MUTANTS])
def test_negative_cases_catch_naive_brand_direct_rules(monkeypatch, mutant, case, kwargs):
    import app.workflow.runtime as runtime
    monkeypatch.setattr(runtime, "decide", mutant)
    with pytest.raises(AssertionError):
        globals()[case](**kwargs)
