"""Offline regressions for LIVE-01: promise rows empty on a tracked brand-store URL.

Synthetic fixtures only; no live Tavily or xAI calls.
"""
import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from app.research.promise_extractor import PromiseExtractor, XAIPromiseCompletionClient
from app.research.promises import collect_promise_sources
from app.research.provider import SourceRecord
from app.research.url_safety import same_page_key, strip_tracking
from app.services.tavily import TavilyProvider

# Shape of the LIVE-01 listing URL (values synthetic).
LISTING = ("https://www.lelabofragrances.com/santal-33-147.html?bvstate=pg:2/ct:r"
           "&gad_source=1&gad_campaignid=123456789&gbraid=0AAAAAD_synthetic_gbraid"
           "&gclid=Cj0KCQjw_synthetic_gclid_value_BwE&utm_source=google&utm_medium=cpc"
           "&source=shoppingads")
CLEAN = "https://www.lelabofragrances.com/santal-33-147.html?bvstate=pg%3A2%2Fct%3Ar"
PAGE_TEXT = "SECRET-PAGE-TEXT Free standard shipping on all orders. Returns accepted within 30 days."


def run(coro):
    return asyncio.run(coro)


def test_strip_tracking_removes_le_labo_ad_params_and_keeps_content_params():
    stripped = strip_tracking(LISTING)
    parts = urlsplit(stripped)
    assert (parts.hostname, parts.path) == ("www.lelabofragrances.com", "/santal-33-147.html")
    assert parse_qsl(parts.query) == [("bvstate", "pg:2/ct:r")]
    for name in ("gclid", "gbraid", "gad_source", "gad_campaignid", "utm_", "shoppingads"):
        assert name not in stripped
    # Untracked URLs are returned unchanged, and `source` with another value is content.
    assert strip_tracking("https://shop.com/item?size=100ml") == "https://shop.com/item?size=100ml"
    assert strip_tracking("https://shop.com/item?source=catalog") == "https://shop.com/item?source=catalog"


def test_promise_collection_sends_stripped_listing_and_same_seller_urls():
    plan = SimpleNamespace(product_url=LISTING, requires_user_input=False)
    seen = []

    class Provider:
        async def extract_sources(self, urls):
            seen.extend(urls)
            return []

    async def validator(url):
        return url

    search = [SourceRecord("https://lelabofragrances.com/terms?gclid=abc", "Fixture", "terms", datetime.now(timezone.utc))]
    result = run(collect_promise_sources(Provider(), plan, search, destination_validator=validator))
    assert seen == [CLEAN, "https://lelabofragrances.com/terms"]
    assert result.requested == 2
    assert all("gclid" not in url for url in seen)


def extract_with(returned_url, admitted=CLEAN):
    def handler(request):
        assert json.loads(request.content)["urls"] == [admitted]
        return httpx.Response(200, json={"results": [{"url": returned_url, "raw_content": PAGE_TEXT}]})
    return run(TavilyProvider("fixture", transport=httpx.MockTransport(handler)).extract_sources([admitted]))


@pytest.mark.parametrize("returned", [
    CLEAN,
    "https://lelabofragrances.com/santal-33-147.html?bvstate=pg%3A2%2Fct%3Ar",  # www dropped
    "https://www.lelabofragrances.com/santal-33-147.html/?bvstate=pg:2/ct:r",  # slash, decoded query
    "https://www.lelabofragrances.com/santal-33-147.html?gclid=x&bvstate=pg%3A2%2Fct%3Ar&utm_source=g",  # tracking back
    "http://www.lelabofragrances.com/santal-33-147.html?bvstate=pg%3A2%2Fct%3Ar",  # scheme
])
def test_tavily_respelled_same_page_is_accepted_under_admitted_url(returned):
    records = extract_with(returned)
    assert len(records) == 1
    assert records[0].source_url == CLEAN
    assert records[0].content_kind == "merchant_page"


@pytest.mark.parametrize("returned", [
    "https://lelabo-outlet-sale.com/santal-33-147.html?bvstate=pg%3A2%2Fct%3Ar",  # lookalike host
    "https://shop.lelabofragrances.com/santal-33-147.html?bvstate=pg%3A2%2Fct%3Ar",  # other subdomain
    "https://www.lelabofragrances.com/another-33-100.html?bvstate=pg%3A2%2Fct%3Ar",  # other path
    "https://www.lelabofragrances.com/santal-33-147.html?bvstate=pg%3A3",  # other content query
    "https://www.lelabofragrances.com/santal-33-147.html",  # content query dropped
    "http://127.0.0.1/santal-33-147.html",  # private destination
])
def test_tavily_different_page_is_still_rejected(returned):
    assert extract_with(returned) == []


def test_same_page_key_does_not_collapse_hosts_or_paths():
    assert same_page_key("https://www.a.com/x/") == same_page_key("https://a.com/x")
    assert same_page_key("https://a.com/x") != same_page_key("https://b.com/x")
    assert same_page_key("https://a.com/x") != same_page_key("https://a.com/x/y")


def promise_inputs():
    source = SourceRecord(CLEAN, "Retrieved merchant page", PAGE_TEXT, datetime.now(timezone.utc), content_kind="merchant_page")
    plan = SimpleNamespace(product_url=CLEAN)
    collection = SimpleNamespace(status="partial", records=[source], requested=3)
    return plan, source, collection


def explanations(sheet):
    return [row.explanation for row in sheet.records if row.status == "unavailable"]


def test_truncated_grok_reply_gives_cut_off_diagnostic():
    plan, source, collection = promise_inputs()
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": '{"records": [{"topic": "ret'}}]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reader = XAIPromiseCompletionClient(client, api_key="mock-key", model="explicit-test-model")
            return await PromiseExtractor(reader, data_mode="mock").extract(plan, [source], collection=collection)

    sheet = run(go())
    assert len(bodies) == 1 and bodies[0]["max_tokens"] == 4000
    notes = explanations(sheet)
    assert len(notes) == 5
    assert all("page extract returned 1 of 3 pages; promise reader output was cut off." in n for n in notes)


class Reader:
    def __init__(self, result):
        self.result = result

    async def complete(self, message, schema):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize("reader, status, expected", [
    (Reader(TimeoutError()), "partial", "promise reader timed out"),
    (Reader(httpx.ConnectError("x")), "partial", "promise reader request failed"),
    (Reader("not json " + PAGE_TEXT), "partial", "promise reader output was invalid"),
    (Reader(json.dumps({"records": [{"topic": "returns", "status": "supported_as_statement",
                                     "explanation": "invented", "quotes": [{"source_id": "source_1", "quote": "Never stated"}]}]})),
     "partial", "promise reader proposed 1 rows, 0 kept after quote checks"),
    (None, "timeout", "page extract timed out; promise reader not called (no merchant page retrieved)"),
    (None, "unsafe_url", "listing URL was not safe to extract"),
])
def test_diagnostics_never_contain_urls_or_page_text(reader, status, expected):
    plan, source, collection = promise_inputs()
    records = [source] if reader is not None else []
    collection = SimpleNamespace(status=status, records=records, requested=collection.requested)
    sheet = run(PromiseExtractor(reader, data_mode="mock").extract(plan, records, collection=collection))
    notes = explanations(sheet)
    assert notes and all(expected in n for n in notes)
    for note in notes:
        for leaked in ("http", "lelabo", "www.", ".com", "SECRET-PAGE-TEXT", "Free standard shipping", "gclid", "Never stated"):
            assert leaked not in note


def test_diagnostics_only_on_live_path():
    plan, source, _ = promise_inputs()
    sheet = run(PromiseExtractor(Reader(TimeoutError()), data_mode="mock").extract(plan, [source]))
    assert all("Check details" not in n for n in explanations(sheet))


def _status_error(code):
    request = httpx.Request("POST", "https://api.x.ai/v1/chat/completions")
    return httpx.HTTPStatusError("x", request=request, response=httpx.Response(code, request=request))


@pytest.mark.parametrize("error, expected", [
    (httpx.ReadTimeout("x"), "promise reader request timed out"),
    (httpx.ConnectTimeout("x"), "promise reader request timed out"),
    (_status_error(400), "promise reader request failed (HTTP 400)"),
    (_status_error(429), "promise reader request failed (HTTP 429)"),
    (httpx.ConnectError("x"), "promise reader request failed."),
])
def test_reader_failure_causes_are_distinguished(error, expected):
    plan, source, collection = promise_inputs()
    sheet = run(PromiseExtractor(Reader(error), data_mode="mock").extract(plan, [source], collection=collection))
    notes = explanations(sheet)
    assert len(notes) == 5 and all(expected in n for n in notes)


@pytest.mark.parametrize("code, body, expected", [
    (400, {"error": "Invalid response_format json_schema: SECRET-PAGE-TEXT lelabo.com"}, "(HTTP 400, schema rejected)"),
    (400, {"error": "This model's maximum prompt length is 131072 tokens. https://www.lelabofragrances.com"}, "(HTTP 400, input too long)"),
    (404, {"error": "The model explicit-test-model does not exist"}, "(HTTP 404, model unavailable)"),
    (500, {"error": "SECRET-PAGE-TEXT gclid internal"}, "(HTTP 500)"),
])
def test_provider_error_body_maps_to_fixed_hint_without_leaking(code, body, expected):
    plan, source, collection = promise_inputs()

    def handler(request):
        return httpx.Response(code, json=body)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reader = XAIPromiseCompletionClient(client, api_key="mock-key", model="explicit-test-model")
            return await PromiseExtractor(reader, data_mode="mock").extract(plan, [source], collection=collection)

    notes = explanations(run(go()))
    assert len(notes) == 5 and all(f"promise reader request failed {expected}." in n for n in notes)
    for note in notes:
        for leaked in ("http:", "https", "lelabo", ".com", "SECRET-PAGE-TEXT", "gclid", "131072", "explicit-test-model"):
            assert leaked not in note
