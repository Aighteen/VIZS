"""Reviewer (lane E) regressions for commit 0cf68ed. Offline, synthetic fixtures only."""
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.decision.promises import validate_promise_sheet
from app.models import PromiseSheet, PromiseSource
from app.research.promise_extractor import PromiseExtractor, XAIPromiseCompletionClient
from app.research.provider import SourceRecord
from app.research.url_safety import same_page_key, strip_tracking
from app.services.tavily import TavilyProvider

ADMITTED = "https://www.lelabofragrances.com/santal-33-147.html"


# strip_tracking promises "every other query parameter is kept in order"; it
# must not respell content parameters while removing tracking ones.
@pytest.mark.parametrize("tracked, expected", [
    ("https://shop.example.org/p?q=%E9t%E9&gclid=1", "https://shop.example.org/p?q=%E9t%E9"),  # non-UTF-8 bytes
    ("https://shop.example.org/p?sku&gclid=1", "https://shop.example.org/p?sku"),  # bare key
    ("https://shop.example.org/p?a=1;b=2&utm_source=x", "https://shop.example.org/p?a=1;b=2"),  # ';' kept
    ("https://shop.example.org/p?q=a%20b&gad_source=1&size=50ml", "https://shop.example.org/p?q=a%20b&size=50ml"),
    ("https://shop.example.org/p?gclid=1&q=%2B1&utm_medium=cpc", "https://shop.example.org/p?q=%2B1"),
])
def test_strip_tracking_keeps_content_params_verbatim(tracked, expected):
    assert strip_tracking(tracked) == expected


def test_stripped_url_still_matches_its_provider_spelling():
    for url in ("https://shop.example.org/p?q=%E9t%E9&gclid=1", "https://shop.example.org/p?sku&gclid=1"):
        assert same_page_key(strip_tracking(url)) == same_page_key(url)


# Provider substitution must never be accepted as the requested page.
@pytest.mark.parametrize("returned", [
    "https://lelabofragrances.co/santal-33-147.html",
    "https://le-labo-fragrances.shop/santal-33-147.html",
    "https://lelabofragrances.com.evil.io/santal-33-147.html",
    "https://www.lelabofragrances.com.evil.io/santal-33-147.html",
    "https://xn--llabofragrances-4nm.com/santal-33-147.html",  # Cyrillic e, punycode
    "https://lеlabofragrances.com/santal-33-147.html",  # Cyrillic e, raw IDN
    "https://www.lelabofragrances.com@evil.io/santal-33-147.html",  # userinfo
    "https://www.lelabofragrances.com:8443/santal-33-147.html",  # port
    "https://evil.io/santal-33-147.html?next=https://www.lelabofragrances.com/santal-33-147.html",
    "https://www.lelabofragrances.com/x/../santal-33-147.html",  # dot segments are not normalized
    "https://www.lelabofragrances.com/santal-33-147.html%3Fvariant%3D2",  # encoded '?' is path
    None,
    42,
])
def test_tavily_extract_rejects_substituted_destination(returned):
    def handler(request):
        return httpx.Response(200, json={"results": [{"url": returned, "raw_content": "page"}]})
    provider = TavilyProvider("fixture", transport=httpx.MockTransport(handler))
    assert asyncio.run(provider.extract_sources([ADMITTED])) == []


@pytest.mark.parametrize("returned", [
    "HTTPS://WWW.LELABOFRAGRANCES.COM./santal-33-147.html#reviews",
    "https://lelabofragrances.com:443/santal-33-147.html",
    "https://www.lelabofragrances.com/santal%2D33-147.html",
])
def test_tavily_extract_accepts_harmless_respelling_under_admitted_url(returned):
    def handler(request):
        return httpx.Response(200, json={"results": [{"url": returned, "raw_content": "page"}]})
    provider = TavilyProvider("fixture", transport=httpx.MockTransport(handler))
    records = asyncio.run(provider.extract_sources([ADMITTED]))
    assert [r.source_url for r in records] == [ADMITTED]


# Promise reader transport failures: a transport read timeout is a timeout, and an
# HTTP rejection names only its numeric status (no body, URL or page text).
def _reader_note(handler):
    source = SourceRecord(ADMITTED, "Retrieved merchant page", "SECRET-PAGE-TEXT Returns within 30 days.",
                          datetime.now(timezone.utc), content_kind="merchant_page")
    plan = SimpleNamespace(product_url=ADMITTED)
    collection = SimpleNamespace(status="partial", records=[source], requested=3)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reader = XAIPromiseCompletionClient(client, api_key="mock-key", model="explicit-test-model")
            return await PromiseExtractor(reader, data_mode="mock").extract(plan, [source], collection=collection)

    notes = [r.explanation for r in asyncio.run(go()).records if r.status == "unavailable"]
    assert len(notes) == 5 and len(set(notes)) == 1
    return notes[0].split("Check details: ", 1)[1]


def _raise(exc_type):
    def handler(request):
        raise exc_type("synthetic", request=request)
    return handler


@pytest.mark.parametrize("handler, expected", [
    (_raise(httpx.ReadTimeout), "promise reader timed out."),
    (_raise(httpx.ConnectTimeout), "promise reader timed out."),
    (_raise(httpx.ConnectError), "promise reader request failed."),
    (lambda request: httpx.Response(400, json={"error": "SECRET-PAGE-TEXT https://x.example"}),
     "promise reader request failed (HTTP 400)."),
    (lambda request: httpx.Response(429, text="rate limited"), "promise reader request failed (HTTP 429)."),
    (lambda request: httpx.Response(503), "promise reader request failed (HTTP 503)."),
])
def test_promise_reader_transport_failures_are_distinguished(handler, expected):
    note = _reader_note(handler)
    assert note.endswith(expected)
    for leaked in ("http", "SECRET", "lelabo", "rate limited", "synthetic"):
        assert leaked not in note.replace("(HTTP ", "")


def test_oversize_reader_reply_is_invalid_not_a_crash():
    note = _reader_note(lambda request: httpx.Response(200, content=b'{"choices": [' + b" " * 33000 + b"]}"))
    assert note.endswith("promise reader output was invalid.")


# Threat-model acceptance tests for the promise-reader fix (docs/reviews/
# BRAND_DIRECT_THREAT_MODEL.md P4-P6). They document weaknesses verified on
# 0cf68ed; strict xfail fails once fixed, so the fixer removes the marker.
_POLICY = "Final sale. No returns. Ships in 30 business days from our warehouse. Prices in USD."


def _kept(quote, region=None):
    source = PromiseSource(source_id="source_1", url="https://shop.example.org/p", retrieved_at=datetime.now(timezone.utc),
                           content=_POLICY, content_kind="merchant_page", seller_domain="shop.example.org", data_mode="mock")
    sheet = PromiseSheet.model_validate({"seller_domain": "shop.example.org", "records": [
        {"topic": "returns", "status": "supported_as_statement", "explanation": "x", "merchant_statement": quote,
         "quotes": [{"source_id": "source_1", "quote": quote}], "conditions": {"region": region}}]})
    return validate_promise_sheet(sheet, sources=[source], seller_domain="shop.example.org").records


def test_exact_clause_quote_is_kept():
    assert len(_kept("Ships in 30 business days from our warehouse.")) == 1


@pytest.mark.xfail(strict=True, reason="P4: quote 'returns' from 'No returns.' drops the negation")
def test_negation_dropping_quote_is_rejected():
    assert _kept("returns") == []


@pytest.mark.xfail(strict=True, reason="P5: any 1-character span is accepted as a quote")
def test_trivial_quote_is_rejected():
    assert _kept("e") == []


@pytest.mark.xfail(strict=True, reason="P6: region 'US' matches inside 'USD'")
def test_region_condition_needs_word_boundary():
    assert _kept("Ships in 30 business days from our warehouse.", region="US") == []
