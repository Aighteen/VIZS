"""Offline: promise rows survive from retrieved page to reader input, validation and reply.

Synthetic fixtures only; no live Tavily or xAI calls.
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.decision import format_sms, validate_promise_sheet
from app.decision.promises import exact_span
from app.models import Assessment, PromiseSheet, PromiseSource
from app.research.promise_extractor import (PASSAGE_CHARS, READER_CHARS, PromiseExtractor,
                                            XAIPromiseCompletionClient, policy_text, reader_message)
from app.research.promises import collect_promise_sources
from app.research.provider import SourceRecord

SELLER = "synthetic-shop.com"
LISTING = f"https://www.{SELLER}/santal-33.html"
TERMS = f"https://www.{SELLER}/terms-and-conditions"
# Real pages use curly apostrophes, non-breaking spaces and hard line breaks.
TERMS_TEXT = ("Home  |  Account  |  Bag\n"
              "Terms & Conditions of Sale\n"
              "Orders are processed within 1–2 business days.\n"
              "Standard delivery takes 3 to 5 business days once your order has shipped.\n"
              "We’ll accept returns of unused products within 30 days\n   of delivery for a full refund.\n"
              "Return shipping is free with the prepaid label included in your parcel.\n"
              "Follow us on Instagram\n")
LISTING_TEXT = "Santal 33 eau de parfum 100 ml\nAdd to bag\nFree standard shipping on all orders.\n"


def run(coro):
    return asyncio.run(coro)


def page(url, text, kind="merchant_page"):
    return SourceRecord(url, "Retrieved merchant page", text, datetime.now(timezone.utc), content_kind=kind)


def registry_source(content, source_id="a", url=TERMS, kind="merchant_page"):
    return PromiseSource(source_id=source_id, url=url, retrieved_at=datetime.now(timezone.utc),
                         content=content, content_kind=kind, seller_domain=SELLER)


def row(topic, quote, *, source_id="a", statement=None, conditions=None):
    return {"topic": topic, "status": "supported_as_statement", "explanation": "x",
            "merchant_statement": statement, "quotes": [{"source_id": source_id, "quote": quote}],
            "conditions": conditions or {}}


def check(rows, content=TERMS_TEXT):
    source = registry_source(content)
    sheet = PromiseSheet.model_validate({"seller_domain": SELLER, "records": rows})
    return validate_promise_sheet(sheet, [source], SELLER)


# ---------------------------------------------------------------- quote validation

@pytest.mark.parametrize("model_quote, page_span", [
    # Straight apostrophe for the page's curly one, line break collapsed to a space.
    ("We'll accept returns of unused products within 30 days of delivery for a full refund.",
     "We’ll accept returns of unused products within 30 days\n   of delivery for a full refund."),
    # Plain spaces for the page's non-breaking spaces.
    ("Standard delivery takes 3 to 5 business days once your order has shipped.",
     "Standard delivery takes 3 to 5 business days once your order has shipped."),
    # Exact text is unchanged.
    ("Return shipping is free with the prepaid label included in your parcel.",
     "Return shipping is free with the prepaid label included in your parcel."),
])
def test_typographic_differences_are_accepted_and_page_characters_are_kept(model_quote, page_span):
    checked = check([row("returns", model_quote, statement=model_quote)])
    assert len(checked.records) == 1
    kept = checked.records[0]
    assert kept.quotes[0].quote == page_span
    assert kept.quotes[0].quote in TERMS_TEXT
    assert kept.merchant_statement == page_span


@pytest.mark.parametrize("invented", [
    "We'll accept returns of unused products within 60 days of delivery for a full refund.",  # digit
    "We'll accept returns of all products within 30 days of delivery for a full refund.",  # word
    "Orders are processed within 1-2 business days.",  # dash is not typography
    "Return shipping is free with the prepaid label included…",  # ellipsis
    "Return shipping is always free with the prepaid label included in your parcel.",  # added word
    "Orders are processed within 1–2 business days. Return shipping is free",  # non-adjacent lines joined
])
def test_invented_or_altered_quotes_are_still_rejected(invented):
    assert not check([row("returns", invented)]).records


def test_quote_across_two_sources_or_wrong_source_is_rejected():
    other = "Gift wrapping is available."
    sheet = PromiseSheet.model_validate({"seller_domain": SELLER, "records": [
        row("returns", "Gift wrapping is available.", source_id="a")]})
    sources = [registry_source(TERMS_TEXT, "a"), registry_source(other, "b", url=LISTING)]
    assert not validate_promise_sheet(sheet, sources, SELLER).records


def test_conditions_and_statement_must_be_spans_up_to_typography():
    quote = "We’ll accept returns of unused products within 30 days\n   of delivery for a full refund."
    ok = check([row("returns", quote, conditions={"time": "within 30  days of delivery", "eligibility": "unused products"})])
    assert ok.records and ok.records[0].conditions.time == "within 30 days\n   of delivery"
    assert not check([row("returns", quote, conditions={"region": "United States"})]).records
    assert not check([row("returns", quote, statement="Free returns for 90 days.")]).records


def test_exact_span_never_matches_empty_or_whitespace():
    assert exact_span("", TERMS_TEXT) is None
    assert exact_span("  ", TERMS_TEXT) is None
    assert exact_span("free returns", "Free returns") is None  # case is content


# ---------------------------------------------------------------- reader input

def test_policy_text_keeps_policy_lines_and_drops_page_chrome():
    text = policy_text(TERMS_TEXT)
    assert "Follow us on Instagram" not in text and "Home  |  Account" not in text
    for line in ("processed within", "Standard delivery", "accept returns", "Return shipping"):
        assert line in text
    for kept in text.splitlines():
        assert kept in TERMS_TEXT  # every passage is a literal piece of the page


def test_reader_message_is_small_for_three_full_pages():
    filler = ("Lorem ipsum dolor sit amet.\n" * 300)[:11000]
    big = filler + TERMS_TEXT + filler + ("We ship worldwide within 2 days.\n" * 400)
    registry = [registry_source(big[:20000], f"source_{i}", url=f"https://{SELLER}/p{i}") for i in range(3)]
    message = json.loads(reader_message(registry))
    texts = [s["content"] for s in message["sources"]]
    assert all(len(t) <= PASSAGE_CHARS for t in texts)
    assert sum(map(len, texts)) <= READER_CHARS
    assert "Return shipping is free" in texts[0]
    assert "Lorem ipsum" not in "".join(texts)
    assert len(texts[0]) < len(registry[0].content)  # full pages are never sent


def test_page_with_no_policy_text_does_not_call_reader():
    class Never:
        async def complete(self, message, schema):
            raise AssertionError("reader must not be called")
    plan = SimpleNamespace(product_url=LISTING)
    collection = SimpleNamespace(status="partial", records=[page(LISTING, "Santal 33\nAdd to bag")], requested=1)
    sheet = run(PromiseExtractor(Never(), data_mode="mock").extract(plan, collection.records, collection=collection))
    assert all("no policy text in retrieved pages" in r.explanation for r in sheet.records)


def test_policy_pages_are_extracted_before_other_same_seller_pages():
    plan = SimpleNamespace(product_url=LISTING, requires_user_input=False)
    seen = []

    class Provider:
        async def extract_sources(self, urls):
            seen.extend(urls)
            return []

    async def validator(url):
        return url

    now = datetime.now(timezone.utc)
    search = [SourceRecord(f"https://www.{SELLER}/about-us", "Our story", "x", now),
              SourceRecord(f"https://www.{SELLER}/journal", "Journal", "x", now),
              SourceRecord(f"https://www.{SELLER}/shipping-returns", "Shipping & Returns", "x", now)]
    run(collect_promise_sources(Provider(), plan, search, destination_validator=validator))
    assert seen == [LISTING, f"https://www.{SELLER}/shipping-returns", f"https://www.{SELLER}/about-us"]


# ---------------------------------------------------------------- end to end

class Reader:
    def __init__(self, rows):
        self.rows, self.messages = rows, []

    async def complete(self, message, schema):
        self.messages.append(message)
        return json.dumps({"records": self.rows})


def assessment_with(sheet):
    base = Assessment.model_validate_json(Path("tests/fixtures/insufficient.json").read_text())
    return base.model_copy(update={"promise_sheet": sheet, "evidence": []})


def test_rows_survive_from_reader_to_reply_text():
    rows = [row("returns", "We'll accept returns of unused products within 30 days of delivery for a full refund.", source_id="source_2"),
            row("return_cost", "Return shipping is free with the prepaid label included in your parcel.", source_id="source_2"),
            row("processing_time", "Orders are processed within 1–2 business days.", source_id="source_2"),
            row("transit_time", "Standard delivery takes 3 to 5 business days once your order has shipped.", source_id="source_2"),
            row("shipping_origin", "Free standard shipping on all orders.", source_id="source_1")]
    reader = Reader(rows)
    records = [page(LISTING, LISTING_TEXT), page(TERMS, TERMS_TEXT)]
    collection = SimpleNamespace(status="partial", records=records, requested=2)
    plan = SimpleNamespace(product_url=LISTING)
    sheet = run(PromiseExtractor(reader, data_mode="mock").extract(plan, records, collection=collection))
    assert len(reader.messages) == 1 and "Follow us on Instagram" not in reader.messages[0]
    by_topic = {r.topic: r for r in sheet.records}
    for topic in ("returns", "return_cost", "processing_time", "transit_time"):
        assert by_topic[topic].status == "supported_as_statement"
        assert by_topic[topic].quotes[0].quote in TERMS_TEXT
    # No origin wording: an address or shipping offer is not proof of origin (Q4).
    assert by_topic["shipping_origin"].status == "not_disclosed"
    text = format_sms(assessment_with(sheet))
    assert len(text) <= 1000
    assert "Merchant statement (return cost):" in text
    assert "Return shipping is free with the prepaid label included in your parcel." in text
    assert "Merchant statement (returns):" in text
    assert "We’ll accept returns" in text
    # Quoted rows come before rows that could not be checked or were not disclosed.
    assert text.index("Merchant statement") < text.index("shipping origin: not disclosed")
    assert TERMS in text and "Fulfillment unverified" in text


@pytest.mark.parametrize("response, expected", [
    (httpx.Response(400, json={"error": "bad schema"}), "promise reader request failed (HTTP 400)"),
    (httpx.Response(429, json={"error": "slow down"}), "promise reader request failed (HTTP 429)"),
])
def test_reader_http_status_is_reported_without_provider_body(response, expected):
    def handler(request):
        return response

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reader = XAIPromiseCompletionClient(client, api_key="mock-key", model="explicit-test-model")
            records = [page(TERMS, TERMS_TEXT)]
            collection = SimpleNamespace(status="partial", records=records, requested=1)
            return await PromiseExtractor(reader, data_mode="mock").extract(SimpleNamespace(product_url=LISTING), records, collection=collection)

    notes = [r.explanation for r in run(go()).records]
    assert notes and all(expected in n for n in notes)
    assert not any("schema" in n or "slow down" in n or "http" in n for n in notes)


def test_reader_read_timeout_is_reported_as_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reader = XAIPromiseCompletionClient(client, api_key="mock-key", model="explicit-test-model")
            records = [page(TERMS, TERMS_TEXT)]
            collection = SimpleNamespace(status="partial", records=records, requested=1)
            return await PromiseExtractor(reader, data_mode="mock").extract(SimpleNamespace(product_url=LISTING), records, collection=collection)

    records = run(go()).records
    assert all("promise reader timed out" in r.explanation for r in records if r.status == "unavailable")
