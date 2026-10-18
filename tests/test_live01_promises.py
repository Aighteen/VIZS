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
# Kept parameters stay exactly as issued by the merchant (lane E review).
CLEAN = "https://www.lelabofragrances.com/santal-33-147.html?bvstate=pg:2/ct:r"
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
    "https://www.lelabofragrances.com/santal-33-147.html?bvstate=pg%3A2%2Fct%3Ar&color=red",  # content param added
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
    assert len(bodies) == 1 and bodies[0]["max_tokens"] == 2000
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


FILLER = "Santal 33 eau de parfum notes of cardamom iris violet ambrox. " * 400
RETURNS = "Returns are accepted within 30 days of delivery for unopened items."
SHIPPING = "Orders placed before 1pm EST ship the same business day."


def long_page():
    return FILLER + RETURNS + " " + FILLER + SHIPPING + " " + FILLER


def test_long_page_registry_keeps_policy_lines_beyond_the_old_cut():
    from app.research.promise_extractor import source_registry
    plan, source, _ = trimmed_inputs()
    assert len(source.excerpt) > 40000 and source.excerpt.index(SHIPPING) > 20000
    content = source_registry(plan, [source])[0].content
    assert RETURNS in content and SHIPPING in content and "cardamom" not in content


def trimmed_inputs():
    source = SourceRecord(CLEAN, "Retrieved merchant page", long_page(), datetime.now(timezone.utc), content_kind="merchant_page")
    collection = SimpleNamespace(status="partial", records=[source], requested=1)
    return SimpleNamespace(product_url=CLEAN), source, collection


def row(topic, status, *quotes):
    return {"topic": topic, "status": status, "explanation": "x",
            "quotes": [{"source_id": "source_1", "quote": q} for q in quotes]}


def test_reader_receives_trimmed_page_and_exact_quotes_survive():
    plan, source, collection = trimmed_inputs()
    seen = []

    class Capture(Reader):
        async def complete(self, message, schema):
            seen.append(json.loads(message))
            return self.result

    reply = json.dumps({"records": [row("returns", "supported_as_statement", RETURNS)]})
    sheet = run(PromiseExtractor(Capture(reply), data_mode="mock").extract(plan, [source], collection=collection))
    content = seen[0]["sources"][0]["content"]
    assert len(content) <= 2500 and RETURNS in content
    kept = [r for r in sheet.records if r.status == "supported_as_statement"]
    assert [r.topic for r in kept] == ["returns"] and kept[0].quotes[0].quote == RETURNS
    assert "1 rows, 1 kept" in sheet.records[-1].explanation


def test_quote_stitched_across_windows_or_absence_claim_on_trimmed_page_is_dropped():
    from app.research.promise_extractor import source_registry
    plan, source, collection = trimmed_inputs()
    retained = source_registry(plan, [source])[0].content
    gap = retained.index("\n")
    stitched = retained[gap - 20:gap + 30]
    assert stitched in retained and stitched not in source.excerpt
    reply = json.dumps({"records": [row("returns", "supported_as_statement", stitched),
                                    row("shipping_origin", "not_disclosed")]})
    sheet = run(PromiseExtractor(Reader(reply), data_mode="mock").extract(plan, [source], collection=collection))
    assert all(r.status == "unavailable" for r in sheet.records)
    assert "proposed 2 rows, 0 kept" in sheet.records[0].explanation


@pytest.mark.parametrize("evaluation, grok, expected", [(100, 30, 40.0), (100, 60, 10.0), (120, 8, 55.0), (40, 30, 5.0)])
def test_reader_timeout_fits_evaluation_budget(evaluation, grok, expected):
    from app.config import Settings
    from app.research.promise_extractor import reader_timeout
    settings = Settings(evaluation_timeout_seconds=evaluation, grok_timeout_seconds=grok)
    assert reader_timeout(settings) == expected
    assert grok + 10 + 15 + reader_timeout(settings) <= evaluation or expected == 5.0


def test_promise_request_uses_its_own_bounded_timeout():
    timeouts = []

    def handler(request):
        timeouts.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"records": []}'}}]})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=8) as client:
            reader = XAIPromiseCompletionClient(client, api_key="mock-key", model="explicit-test-model", request_timeout=37)
            return await reader.complete("{}", {})

    assert run(go()) == '{"records": []}' and timeouts == [37]
    with pytest.raises(ValueError):
        XAIPromiseCompletionClient(httpx.AsyncClient(), api_key="k", model="m", request_timeout=0)


def test_reader_schema_is_flat_and_its_replies_parse_as_candidates():
    from app.research.promise_extractor import READER_SCHEMA, PromiseCandidates
    text = json.dumps(READER_SCHEMA)
    assert all(k not in text for k in ("$ref", "$defs", "anyOf", "default", '"null"'))

    def required_everywhere(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert set(node["required"]) == set(node["properties"]) and node["additionalProperties"] is False
            for value in node.values():
                required_everywhere(value)
    required_everywhere(READER_SCHEMA)
    reply = {"records": [{"topic": "returns", "status": "supported_as_statement", "explanation": "x",
                          "quotes": [{"source_id": "source_1", "quote": "Returns within 30 days."}]}]}
    assert PromiseCandidates.model_validate(reply).records[0].topic == "returns"


@pytest.mark.parametrize("elapsed, expected", [(10, 55.0), (45, 45.0), (88, 5.0), (0, 55.0)])
def test_reader_timeout_uses_remaining_budget(elapsed, expected):
    from app.config import Settings
    from app.research.promise_extractor import reader_timeout
    assert reader_timeout(Settings(evaluation_timeout_seconds=100), elapsed) == expected


def test_runtime_gives_promise_request_the_remaining_budget():
    from tests.test_brand_store_acceptance import LE_LABO, brand_scenario, evaluate, faithful_promises
    seen = []
    inner = faithful_promises(list(LE_LABO.stated.items()))

    def promise(request):
        seen.append(request.extensions["timeout"]["read"])
        return inner(request)

    assessment, _ = evaluate(brand_scenario(LE_LABO, promise=promise))
    # Offline the earlier stages take ~0 s, so the reader gets the 55 s cap, not the plan's 30 s.
    assert len(seen) == 1 and 50 < seen[0] <= 55
    assert any(r.status == "supported_as_statement" for r in assessment.promise_sheet.records)


FALLBACK_PAGE = (
    "Santal 33 Eau de Parfum. Add to bag.\n"
    "Orders are processed within 1-2 business days. Standard delivery takes 3-5 business days.\n"
    "All orders ship from our warehouse in New Jersey.\n"
    "Refunds are processed within 10 days. Unopened items may be returned within 30 days of delivery.\n"
    "Return shipping is free with the prepaid return label.\n"
    "No returns.\n"
)


def fallback_sheet(reader_error, content=FALLBACK_PAGE, kind="merchant_page"):
    source = SourceRecord(CLEAN, "Retrieved merchant page", content, datetime.now(timezone.utc), content_kind=kind)
    collection = SimpleNamespace(status="partial", records=[source], requested=1)
    return run(PromiseExtractor(Reader(reader_error), data_mode="mock").extract(
        SimpleNamespace(product_url=CLEAN), [source], collection=collection)), source


def test_reader_timeout_falls_back_to_whole_policy_sentences():
    sheet, source = fallback_sheet(TimeoutError())
    quotes = {r.topic: r.quotes[0].quote for r in sheet.records if r.status == "supported_as_statement"}
    assert quotes == {
        "shipping_origin": "All orders ship from our warehouse in New Jersey.",
        "processing_time": "Orders are processed within 1-2 business days.",
        "transit_time": "Standard delivery takes 3-5 business days.",
        "returns": "Unopened items may be returned within 30 days of delivery.",
        "return_cost": "Return shipping is free with the prepaid return label.",
    }
    assert all(q in source.excerpt for q in quotes.values())
    assert all(r.explanation == "Merchant statement in retrieved content; fulfillment unverified."
               for r in sheet.records if r.status == "supported_as_statement")


def test_fallback_is_only_for_timeouts_and_only_quotes_merchant_pages():
    sheet, _ = fallback_sheet(httpx.ConnectError("x"))
    assert all(r.status == "unavailable" for r in sheet.records)
    sheet, _ = fallback_sheet("not json")
    assert all(r.status == "unavailable" for r in sheet.records)
    sheet, _ = fallback_sheet(TimeoutError(), kind="search_snippet")
    assert all(r.status == "unavailable" for r in sheet.records)
    sheet, _ = fallback_sheet(TimeoutError(), content="Santal 33. Free shipping on every order. Notes of cardamom.")
    assert all(r.status == "unavailable" for r in sheet.records)
    assert all("promise reader timed out; 0 rows taken from page wording." in r.explanation for r in sheet.records)


VARIANT = "https://www.allbirds.com/products/mens-wool-runners?variant=40195939811408"
PRODUCT = "https://www.allbirds.com/products/mens-wool-runners"


@pytest.mark.parametrize("returned", [PRODUCT, PRODUCT + "/", PRODUCT + "#details", "https://allbirds.com/products/mens-wool-runners"])
def test_canonical_answer_for_variant_listing_is_kept_under_the_canonical_url(returned):
    records = extract_with(returned, admitted=VARIANT)
    assert len(records) == 1 and records[0].source_url == returned.split("#")[0]
    # Dropping the content query is the canonical page of the same product (lane A).
    assert [r.source_url for r in extract_with(CLEAN.split("?")[0])] == [CLEAN.split("?")[0]]


@pytest.mark.parametrize("returned", [
    PRODUCT + "?variant=1",  # different variant: changed, not dropped
    PRODUCT + "?variant=40195939811408&size=9",  # added parameter
    "https://www.allbirds.com/products/womens-wool-runners",  # other path
    "https://shop.allbirds.com/products/mens-wool-runners",  # other host
    "https://allbirds.co/products/mens-wool-runners",  # lookalike
    "https://www.allbirds.com/collections/mens",  # other page
])
def test_canonical_rule_never_crosses_hosts_paths_or_variants(returned):
    assert extract_with(returned, admitted=VARIANT) == []


def test_canonical_rule_needs_one_unambiguous_request():
    def handler(request):
        return httpx.Response(200, json={"results": [{"url": PRODUCT, "raw_content": PAGE_TEXT}]})
    provider = TavilyProvider("fixture", transport=httpx.MockTransport(handler))
    assert run(provider.extract_sources([VARIANT, PRODUCT + "?variant=2"])) == []


REGIONAL_PAGE = (
    "HOME DELIVERY\n"
    "Free standard shipping on orders €100+ (2–3 business days)\n"
    "Free standard shipping on orders £100+ (3–4 business days)\n"
    "Free standard shipping on orders $35+ (5–7 business days)\n"
    "Final Sale items cannot be returned, canceled, or exchanged.\n"
    "Unworn shoes can be returned within 30 days of delivery.\n"
    "Return shipping is free for US orders.\n"
    "Return shipping is free for UK orders.\n"
)


def fallback_rows(listing, content=REGIONAL_PAGE):
    from app.research.promise_extractor import lexical_candidates, source_registry
    source = SourceRecord(listing, "Retrieved merchant page", content, datetime.now(timezone.utc), content_kind="merchant_page")
    rows = lexical_candidates(source_registry(SimpleNamespace(product_url=listing), [source]), listing)
    return {r.topic: (r.quotes[0].quote, r.conditions.region, r.conditions.eligibility) for r in rows}


def test_fallback_quotes_the_listing_region_and_the_general_rule():
    rows = fallback_rows("https://www.shop-synthetic.com/products/runner")
    assert rows["transit_time"] == ("Free standard shipping on orders $35+ (5–7 business days)", None, None)
    assert rows["returns"] == ("Unworn shoes can be returned within 30 days of delivery.", None, None)
    assert rows["return_cost"] == ("Return shipping is free for US orders.", "US", None)


@pytest.mark.parametrize("listing, transit, cost", [
    ("https://www.shop-synthetic.co.uk/products/runner", "£100+", "UK orders"),
    ("https://www.shop-synthetic.com/uk/products/runner", "£100+", "UK orders"),
    ("https://www.shop-synthetic.com/fr/products/runner", "€100+", None),
])
def test_fallback_region_follows_cctld_or_locale_path(listing, transit, cost):
    rows = fallback_rows(listing)
    assert transit in rows["transit_time"][0]
    assert (cost in rows["return_cost"][0]) if cost else "return_cost" not in rows


def test_special_case_is_used_only_as_a_last_resort_and_named_as_eligibility():
    rows = fallback_rows("https://www.shop-synthetic.com/p", "Final Sale items cannot be returned, canceled, or exchanged.\n")
    assert rows["returns"] == ("Final Sale items cannot be returned, canceled, or exchanged.", None, "Final Sale items")


def test_fallback_conditions_survive_validation_and_show_in_reply():
    from app.decision.promises import validate_promise_sheet
    from app.research.promise_extractor import lexical_candidates, source_registry
    from app.models import PromiseSheet
    listing = "https://www.shop-synthetic.com/products/runner"
    source = SourceRecord(listing, "Retrieved merchant page", REGIONAL_PAGE, datetime.now(timezone.utc), content_kind="merchant_page")
    registry = source_registry(SimpleNamespace(product_url=listing), [source])
    sheet = validate_promise_sheet(PromiseSheet(seller_domain="shop-synthetic.com", sources=registry,
                                                records=lexical_candidates(registry, listing)),
                                   sources=registry, seller_domain="shop-synthetic.com")
    cost = next(r for r in sheet.records if r.topic == "return_cost")
    assert cost.conditions.region == "US" and len(sheet.records) == 3


@pytest.mark.parametrize("environ, plan_model, promise_model", [
    ({"XAI_MODEL": "plan-model-synthetic"}, "plan-model-synthetic", "plan-model-synthetic"),
    ({"XAI_MODEL": "plan-model-synthetic", "XAI_PROMISE_MODEL": "  "}, "plan-model-synthetic", "plan-model-synthetic"),
    ({"XAI_MODEL": "plan-model-synthetic", "XAI_PROMISE_MODEL": "reader-model-synthetic"}, "plan-model-synthetic", "reader-model-synthetic"),
])
def test_promise_model_setting_falls_back_to_xai_model(tmp_path, environ, plan_model, promise_model):
    from app.config import Settings
    settings = Settings.from_env(tmp_path / "absent.env", environ=environ)
    assert settings.xai_model == plan_model and settings.promise_model == promise_model


@pytest.mark.parametrize("promise_setting, expected", [("", "qa-synthetic-model"), ("reader-model-synthetic", "reader-model-synthetic")])
def test_runtime_sends_promise_model_only_to_the_reader(promise_setting, expected):
    from tests.test_brand_store_acceptance import LE_LABO, brand_scenario, evaluate, live_settings
    models = {}
    scenario = brand_scenario(LE_LABO)
    handler = scenario.handler

    def recording(request):
        if request.url.host == "api.x.ai":
            body = json.loads(request.content)
            models[body["response_format"]["json_schema"]["name"]] = body["model"]
        return handler(request)

    scenario.handler = recording
    evaluate(scenario, live_settings(xai_promise_model=promise_setting))
    assert models == {"shopping_plan": "qa-synthetic-model", "promise_records": expected}


def test_member_and_opt_in_terms_are_named_and_issue_deadlines_are_not_transit():
    page = ("Free standard shipping on orders $50+ and free 60-day returns for Nike Members.\n"
            "When you opt-in for coverage at checkout, your return label is included for free.\n"
            "For order issues, contact us within 7 days of delivery with a photo.\n")
    rows = fallback_rows("https://www.shop-synthetic.com/t/shoe", page)
    assert rows["returns"][2] == "for Nike Members"
    assert rows["return_cost"] == ("When you opt-in for coverage at checkout, your return label is included for free.", None, "opt-in")
    assert "transit_time" not in rows
