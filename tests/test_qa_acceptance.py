"""QA acceptance tests that encode docs/ACCEPTANCE_TESTS.md for the backend.

All data is SYNTHETIC. Every provider (xAI, Tavily, Verisign RDAP) is replaced by
an httpx.MockTransport; the destination validator is injected so no DNS lookup
happens. Nothing here is live research or sponsor usage.

Tests marked xfail(strict=True) are tracked product defects (QA-xx ids in
docs/QA_REPORT.md); the test encodes the specification, not current behavior.
"""
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.decision import decide, format_sms, validate_promise_sheet
from app.main import create_app
from app.models import (Assessment, Decision, Evidence, OrchestratorPlan, PromiseContext,
                        PromiseSheet, PromiseSource, Risk, ShoppingRequest)
from app.research.promise_extractor import PROMISE_PROMPT, PromiseExtractor
from app.research.provider import ResearchUnavailable, SourceRecord
from app.research.url_safety import UnsafeURL, public_url, validate_public_destination
from app.services.tavily import TavilyProvider

QA = Path(__file__).parent / "qa_fixtures"
FIXTURES = Path(__file__).parent / "fixtures"

SELLER = "synthetic-shop.com"
LISTING = f"https://{SELLER}/perfume/qa"
TOKEN = "qa-synthetic-pairing-token"
XAI_KEY = "qa-synthetic-xai-key-do-not-use"
TAVILY_KEY = "qa-synthetic-tavily-key-do-not-use"
NOW = "2026-10-17T12:00:00Z"

URL_RE = re.compile(r"https?://[^\s\"'<>]+")

# Output must never accuse, claim certainty, or give probabilities (AGENTS.md
# risk taxonomy; CREDIBILITY_CHECKING.md deterministic response rules).
BANNED = [
    r"\d+(?:\.\d+)?\s*%", r"\bpercent\b", r"\bprobabilit", r"\bscam", r"\bcounterfeit",
    r"\bfake\b", r"\bfraudulent\b", r"\b(?:is|are) (?:a )?fraud\b", r"\bguarantee",
    r"\bauthentic(?:ity)? (?:is )?(?:verified|confirmed|guaranteed)\b", r"\b100% genuine\b",
]


def assert_no_accusation(text):
    for pattern in BANNED:
        assert not re.search(pattern, text, re.IGNORECASE), f"banned wording {pattern!r} in: {text}"


def chat(content, **message):
    if not isinstance(content, str):
        content = json.dumps(content)
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": content, **message}}]})


def plan_output(**changes):
    value = {"request_id": "backend", "intent": "evaluate_purchase", "product_url": LISTING,
             "tasks": [{"kind": "verify_seller", "query": "model-authored query"}]}
    value.update(changes)
    return value


def live_settings(**changes):
    values = dict(provider_mode="live", xai_api_key=XAI_KEY, xai_model="qa-synthetic-model",
                  tavily_api_key=TAVILY_KEY, extension_token=TOKEN)
    values.update(changes)
    return Settings(**values)


class Harness:
    """Assembled runtime (real contracts, extractor, research, policy, formatter)
    behind the HTTP API with every outbound request answered by synthetic data."""

    def __init__(self, *, plan=None, promise=None, search=None, extract=None, rdap=None,
                 settings=None, validator=None):
        self.plan = plan_output() if plan is None else plan
        self.promise = {"records": []} if promise is None else promise
        self.search = [] if search is None else search
        self.extract = [] if extract is None else extract
        self.rdap = rdap
        self.settings = settings or live_settings()
        self.validator = validator
        self.calls, self.xai_bodies, self.tavily_bodies, self.dns = [], [], [], []

    @staticmethod
    def _answer(spec, request, default):
        if callable(spec):
            return spec(request)
        if isinstance(spec, httpx.Response):
            return spec
        return default(spec)

    def handler(self, request):
        host, path = request.url.host, request.url.path
        if host == "api.x.ai":
            body = json.loads(request.content)
            name = body["response_format"]["json_schema"]["name"]
            self.calls.append(name)
            self.xai_bodies.append(body)
            return self._answer(self.plan if name == "shopping_plan" else self.promise, request, chat)
        if host == "api.tavily.com":
            self.calls.append(path)
            self.tavily_bodies.append(json.loads(request.content))
            spec = self.search if path == "/search" else self.extract
            return self._answer(spec, request, lambda results: httpx.Response(200, json={"results": results}))
        if host == "rdap.verisign.com":
            self.calls.append("rdap")
            default = {"ldhName": SELLER, "events": [{"eventAction": "registration", "eventDate": "2019-05-01T00:00:00Z"}]}
            return self._answer(self.rdap if self.rdap is not None else default, request,
                                lambda payload: httpx.Response(200, json=payload))
        raise AssertionError(f"Unexpected outbound host: {host}")

    async def destination(self, url):
        self.dns.append(url)
        if self.validator is not None:
            return await self.validator(url)
        return public_url(url)

    def app(self):
        transport = httpx.MockTransport(self.handler)
        return create_app(settings=self.settings, xai_transport=transport, tavily_transport=transport,
                          domain_transport=transport, destination_validator=self.destination)

    def post(self, path="/api/v1/evaluate-message", text=f"Is this perfume seller ok? {LISTING}",
             request_id="qa-request", headers=None):
        with TestClient(self.app()) as client:
            return client.post(path, json={"request_id": request_id, "message_text": text, "channel": "debug"},
                               headers=headers or {})


def row(topic, status, quotes=(), statement=None, explanation="Model wording (not authoritative).", **conditions):
    return {"topic": topic, "status": status, "merchant_statement": statement, "explanation": explanation,
            "quotes": [{"source_id": s, "quote": q} for s, q in quotes], "conditions": conditions}


def source(source_id, url, content, kind="merchant_page", seller=SELLER):
    return {"source_id": source_id, "url": url, "retrieved_at": NOW, "content": content,
            "content_kind": kind, "seller_domain": seller, "data_mode": "mock"}


def base_assessment(**changes):
    data = json.loads((FIXTURES / "insufficient.json").read_text())
    data.update(changes)
    return Assessment.model_validate(data)


def evidence(**changes):
    value = dict(claim="SYNTHETIC claim", source_url="https://regulator-one.com/action", evidence_type="regulatory",
                 claim_status="verified_fact", retrieved_at=NOW, excerpt="SYNTHETIC excerpt", seller_domain=SELLER,
                 finding="substantial_adverse", polarity="supports", data_mode="mock")
    value.update(changes)
    return Evidence.model_validate(value)


def policy_inputs():
    request = ShoppingRequest(request_id="qa-policy", message_text=LISTING)
    plan = OrchestratorPlan(request_id="qa-policy", intent="evaluate_purchase", product_url=LISTING, data_mode="mock")
    return request, plan


CONFLICT_EXTRACT = [
    {"url": LISTING, "raw_content": "Free returns. US customers only."},
    {"url": f"https://{SELLER}/returns", "raw_content": "US customers pay return shipping. Unopened items within 30 days."},
]
CONFLICT_SEARCH = [{"url": f"https://{SELLER}/returns", "title": "Returns", "content": f"{SELLER} returns policy"}]
CONFLICT_ROW = row("return_cost", "conflicting",
                   [("source_1", "Free returns."), ("source_2", "US customers pay return shipping.")],
                   statement="Free returns.",
                   explanation="This store is a scam: 87% likely counterfeit, return costs $25.",
                   region="US", eligibility="Unopened items within 30 days.")


# ---------------------------------------------------------------- INPUT

def test_INPUT_01_valid_listing_binds_identity_price_and_one_seller_task():
    harness = Harness(plan=plan_output(purchase_price="129.99", request_id="model-invented-id"))
    response = harness.post(text=f"Check {LISTING} listed at $129.99", request_id="qa-input-01")
    assert response.status_code == 200
    assessment = response.json()["assessment"]
    assert assessment["request_id"] == "qa-input-01"
    # Price accepted (an unsupported price would fail closed before research).
    assert harness.calls.count("shopping_plan") == 1
    assert harness.calls.count("/search") == 1
    assert harness.dns[0] == LISTING
    query = harness.tavily_bodies[0]["query"]
    assert SELLER in query and "model-authored" not in query
    assert assessment["decision"] == "VERIFY_FIRST"


@pytest.mark.parametrize("text", ["Is this perfume legit? $150",
                                  f"Compare {LISTING} and https://other-seller.com/item"])
def test_INPUT_02_missing_or_ambiguous_url_clarifies_without_research(text):
    harness = Harness()
    response = harness.post(text=text)
    assert response.status_code == 200
    body = response.json()
    assessment = body["assessment"]
    assert assessment["decision"] == "NEED_MORE_INFORMATION"
    assert "one product listing URL" in assessment["summary"]
    assert assessment["evidence"] == [] and assessment["research"] == []
    assert assessment["promise_sheet"] is None
    assert harness.calls == [] and harness.dns == []
    assert assessment["summary"] in body["message_text"]


@pytest.mark.parametrize("plan", [
    plan_output(product_url="https://invented-seller.com/perfume"),
    plan_output(tasks=[{"kind": "verify_seller", "query": "x"}, {"kind": "recommend_card", "query": "x"}]),
    plan_output(purchase_price="99.00"),
    plan_output(brand="InventedBrand"),
    lambda request: chat(plan_output(), tool_calls=[{"type": "function", "function": {"name": "fetch_url", "arguments": "{}"}}]),
], ids=["invented_url", "extra_tool", "invented_price", "invented_brand", "tool_call"])
def test_INPUT_03_model_invented_url_task_or_price_fails_closed(plan):
    harness = Harness(plan=plan)
    response = harness.post(text=f"Check {LISTING}")
    assert response.status_code == 200
    assessment = response.json()["assessment"]
    assert assessment["decision"] == "NEED_MORE_INFORMATION"
    assert assessment["seller_risk"] == "INSUFFICIENT_EVIDENCE"
    assert harness.calls == ["shopping_plan"], "no research tool may run on rejected model output"
    assert harness.dns == []


@pytest.mark.parametrize("reply", [
    lambda request: chat(plan_output(), refusal="QA-PRIVATE-BODY refusal text"),
    lambda request: httpx.Response(500, text="QA-PRIVATE-BODY upstream stack trace"),
    lambda request: httpx.Response(401, json={"error": "QA-PRIVATE-BODY bad key"}),
    lambda request: chat("QA-PRIVATE-BODY not json"),
    lambda request: httpx.Response(200, text="QA-PRIVATE-BODY"),
], ids=["refusal", "http_500", "http_401", "invalid_json_content", "invalid_envelope"])
def test_INPUT_04_provider_refusal_or_invalid_body_is_controlled_and_sanitized(reply):
    harness = Harness(plan=reply)
    response = harness.post()
    assert response.status_code == 200
    assessment = response.json()["assessment"]
    assert assessment["decision"] == "NEED_MORE_INFORMATION"
    assert "QA-PRIVATE-BODY" not in response.text
    assert XAI_KEY not in response.text and TAVILY_KEY not in response.text
    assert harness.calls == ["shopping_plan"]


# ---------------------------------------------------------------- PROM

def test_PROM_01_conflict_cited_in_both_formats_without_accusation_or_invented_cost():
    harness = Harness(search=CONFLICT_SEARCH, extract=CONFLICT_EXTRACT, promise={"records": [CONFLICT_ROW]})
    response = harness.post(path="/api/v1/extension/evaluate", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    body = response.json()
    sheet = body["assessment"]["promise_sheet"]
    conflict = [r for r in sheet["records"] if r["status"] == "conflicting"]
    assert len(conflict) == 1 and len(conflict[0]["quotes"]) == 2
    urls = {s["source_id"]: s["url"] for s in sheet["sources"]}
    for quote in conflict[0]["quotes"]:
        assert quote["quote"] in next(s["content"] for s in sheet["sources"] if s["source_id"] == quote["source_id"])
        assert urls[quote["source_id"]] in body["message_text"]
    assert '"Free returns."' in body["message_text"]
    assert '"US customers pay return shipping."' in body["message_text"]
    assert "$" not in body["message_text"]
    for text in [body["message_text"], body["assessment"]["summary"], *body["assessment"]["missing_information"],
                 *(r["explanation"] for r in sheet["records"])]:
        assert_no_accusation(text)


def test_PROM_02_processing_and_transit_ranges_stay_distinct_without_guarantee():
    data = json.loads((QA / "shipping_ranges.json").read_text())
    assert data["label"].startswith("SYNTHETIC")
    sheet = PromiseSheet.model_validate(data["sheet"])
    checked = validate_promise_sheet(sheet, sheet.sources)
    by_topic = {r.topic: r for r in checked.records}
    assert set(by_topic) == {"processing_time", "transit_time"}
    assert by_topic["processing_time"].conditions.time == "1-2 business days"
    assert by_topic["transit_time"].conditions.time == "3-7 business days"
    assert by_topic["transit_time"].conditions.region == "US"
    text = format_sms(base_assessment(promise_sheet=checked))
    assert '"Orders are processed in 1-2 business days."' in text
    assert '"Standard delivery takes 3-7 business days within the US after dispatch."' in text
    assert "Fulfillment unverified" in text
    assert not re.search(r"guarantee|arrives by|monday|tuesday|wednesday|thursday|friday|tomorrow", text, re.IGNORECASE)
    assert_no_accusation(text)


@pytest.mark.parametrize("bad_row", [
    row("arrival", "supported_as_statement", [("shipping", "Orders are processed in 1-2 business days.")],
        statement="Orders are processed in 1-2 business days.", time="4-9 business days"),
    row("arrival", "supported_as_statement", [("shipping", "Delivery in 4-9 business days.")],
        statement="Delivery in 4-9 business days."),
    row("transit_time", "supported_as_statement", [("shipping", "Delivery times are estimates.")],
        statement="Delivery times are estimates.", region="Canada"),
], ids=["merged_range_condition", "merged_range_quote", "invented_region"])
def test_PROM_02_merged_or_invented_ranges_are_rejected(bad_row):
    data = json.loads((QA / "shipping_ranges.json").read_text())["sheet"]
    data["records"] = [bad_row]
    sheet = PromiseSheet.model_validate(data)
    assert validate_promise_sheet(sheet, sheet.sources).records == []


def test_PROM_03_local_address_without_origin_disclosure_stays_unknown():
    page = SourceRecord(LISTING, "SYNTHETIC listing",
                        "Synthetic Perfume LLC, 100 Pike Street, Seattle, WA. Free returns within 30 days.",
                        datetime.now(timezone.utc), content_kind="merchant_page")
    sheet = asyncio.run(PromiseExtractor(data_mode="mock").extract(SimpleNamespace(product_url=LISTING), [page]))
    origin = [r for r in sheet.records if r.topic == "shipping_origin"]
    assert origin and all(r.status in {"unavailable", "not_disclosed"} for r in origin)
    harness = Harness(extract=[{"url": LISTING, "raw_content": page.excerpt}],
                      promise={"records": [row("returns", "supported_as_statement", [("source_1", "Free returns within 30 days.")],
                                               statement="Free returns within 30 days.")]})
    body = harness.post().json()
    records = {r["topic"]: r for r in body["assessment"]["promise_sheet"]["records"]}
    assert records["shipping_origin"]["status"] in {"unavailable", "not_disclosed"}
    assert not re.search(r"ships? from|local warehouse|shipped locally", body["message_text"], re.IGNORECASE)


def test_PROM_04_not_disclosed_requires_inspected_merchant_page_never_sitewide_absence():
    snippet_only = PromiseSheet.model_validate({"seller_domain": SELLER, "records": [row("returns", "not_disclosed")],
                                                "sources": [source("s1", f"https://{SELLER}/a", "Returns info", kind="search_snippet")]})
    assert validate_promise_sheet(snippet_only, snippet_only.sources).records == []
    inspected = PromiseSheet.model_validate({"seller_domain": SELLER, "records": [row("returns", "not_disclosed")],
                                             "sources": [source("p1", LISTING, "Eau de parfum 50 ml.")]})
    checked = validate_promise_sheet(inspected, inspected.sources)
    assert [r.status for r in checked.records] == ["not_disclosed"]
    assert checked.records[0].explanation == "Not disclosed in inspected sources."
    text = format_sms(base_assessment(promise_sheet=checked))
    assert "not disclosed in inspected source" in text
    assert not re.search(r"no (?:return|shipping) policy|does not (?:have|offer)|site has no|anywhere", text, re.IGNORECASE)


def test_PROM_05_extract_failure_is_unavailable_distinct_from_not_disclosed_and_not_adverse():
    harness = Harness(search=CONFLICT_SEARCH, extract=httpx.Response(503, text="QA-PRIVATE-BODY"),
                      promise={"records": [row("returns", "not_disclosed")]})
    body = harness.post().json()
    assessment = body["assessment"]
    assert "promise_records" not in harness.calls, "no extraction without an inspected merchant page"
    statuses = {r["status"] for r in assessment["promise_sheet"]["records"]}
    assert statuses == {"unavailable"}
    assert "not disclosed" not in body["message_text"]
    assert "check unavailable" in body["message_text"]
    request, plan = policy_inputs()
    baseline = decide(request, plan, [])
    assert (assessment["seller_risk"], assessment["decision"]) == (baseline.seller_risk.value, baseline.decision.value)
    assert "QA-PRIVATE-BODY" not in json.dumps(body)


def test_PROM_06_model_cannot_supply_its_own_source_registry_or_invented_spans():
    output = {"records": [row("returns", "supported_as_statement", [("source_1", "Free returns forever.")],
                              statement="Free returns forever.")],
              "sources": [source("source_1", LISTING, "Free returns forever.")]}
    harness = Harness(extract=CONFLICT_EXTRACT, promise=output)
    sheet = harness.post().json()["assessment"]["promise_sheet"]
    assert all(r["status"] == "unavailable" for r in sheet["records"])
    assert all("forever" not in s["content"] for s in sheet["sources"])
    harness = Harness(extract=CONFLICT_EXTRACT, promise={"records": output["records"]})
    sheet = harness.post().json()["assessment"]["promise_sheet"]
    assert not any(r["status"] == "supported_as_statement" for r in sheet["records"])


def test_PROM_07_unrelated_seller_page_is_excluded():
    foreign = PromiseSheet.model_validate({
        "seller_domain": SELLER,
        "sources": [source("foreign", "https://other-seller.com/returns", "Free returns.")],
        "records": [row("returns", "supported_as_statement", [("foreign", "Free returns.")], statement="Free returns.")]})
    checked = validate_promise_sheet(foreign, foreign.sources)
    assert checked.records == [] and checked.sources == []
    harness = Harness(
        search=[{"url": "https://other-seller.com/returns", "title": "Other", "content": "Other seller returns policy"}],
        extract=[{"url": LISTING, "raw_content": "Eau de parfum."},
                 {"url": "https://other-seller.com/returns", "raw_content": "Free returns."}],
        promise={"records": [row("returns", "supported_as_statement", [("source_2", "Free returns.")], statement="Free returns.")]})
    body = harness.post().json()
    sheet = body["assessment"]["promise_sheet"]
    assert {httpx.URL(s["url"]).host for s in sheet["sources"]} <= {SELLER}
    assert not any(r["status"] == "supported_as_statement" for r in sheet["records"])
    assert body["assessment"]["research"][0]["status"] == "filtered"
    assert all(httpx.URL(u).host == SELLER for u in harness.tavily_bodies[-1]["urls"])


def test_PROM_07_region_scoped_terms_are_qualified_not_merged():
    sheet = PromiseSheet.model_validate({
        "seller_domain": SELLER,
        "sources": [source("a", LISTING, "Free returns for EU orders."),
                    source("b", f"https://{SELLER}/returns", "US customers pay return shipping.")],
        "records": [row("return_cost", "conflicting", [("a", "Free returns for EU orders."), ("b", "US customers pay return shipping.")],
                        region="US")]})
    assert validate_promise_sheet(sheet, sheet.sources).records == []


def test_PROM_08_merchant_self_asserted_authorization_is_statement_only():
    page = "We are an authorized Maison Synthetic retailer. Free returns within 30 days."
    harness = Harness(
        search=[{"url": f"https://{SELLER}/about", "title": "About", "content": f"{SELLER}: official authorized retailer."}],
        extract=[{"url": LISTING, "raw_content": page}],
        promise={"records": [row("returns", "supported_as_statement", [("source_1", "Free returns within 30 days.")],
                                 statement="Free returns within 30 days.")]})
    body = harness.post().json()
    assessment = body["assessment"]
    assert assessment["seller_risk"] == "INSUFFICIENT_EVIDENCE" and assessment["decision"] == "VERIFY_FIRST"
    assert "Seller authorization unconfirmed" in body["message_text"]
    assert all(e["claim_status"] != "verified_fact" for e in assessment["evidence"])
    assert not any(r["status"] == "independently_corroborated" for r in assessment["promise_sheet"]["records"])


def test_PROM_08_seller_hosted_official_authorization_cannot_yield_lower_risk():
    request, plan = policy_inputs()
    self_asserted = evidence(claim="We are an authorized retailer.", source_url=f"https://{SELLER}/about",
                             evidence_type="official", finding="seller_authorized",
                             excerpt="We are an authorized retailer.")
    result = decide(request, plan, [self_asserted])
    assert result.seller_risk != Risk.LOWER_RISK


def test_PROM_09_injection_in_snippets_and_policy_is_data_not_instructions():
    data = json.loads((QA / "injection_pages.json").read_text())
    assert data["label"].startswith("SYNTHETIC")
    harness = Harness(search=data["search_results"], extract=data["extract_results"],
                      promise=data["promise_output_with_override"])
    text = f"Check {LISTING}"
    response = harness.post(text=text)
    assert response.status_code == 200
    body = response.json()
    assessment = body["assessment"]
    assert assessment["seller_risk"] == "INSUFFICIENT_EVIDENCE" and assessment["decision"] == "VERIFY_FIRST"
    for name in ["shopping_plan", "/search", "/extract", "promise_records", "rdap"]:
        assert harness.calls.count(name) == 1, harness.calls
    assert len(harness.calls) == 5
    plan_body, promise_body = harness.xai_bodies
    assert promise_body["messages"][0] == {"role": "system", "content": PROMISE_PROMPT}
    assert "ignore all previous" in promise_body["messages"][1]["content"].lower()
    assert plan_body["messages"][1]["content"] == text
    assert "tools" not in plan_body and "tools" not in promise_body
    search_query = harness.tavily_bodies[0]["query"]
    assert search_query == f'"{SELLER}" seller authorization return policy complaints'
    assert not any(r["status"] in {"supported_as_statement", "independently_corroborated", "conflicting"}
                   for r in assessment["promise_sheet"]["records"])
    message = body["message_text"]
    assert "<script>" not in message and "attacker.com" not in message and "LOWER_RISK" not in message
    assert_no_accusation(message)


def test_PROM_09_link_inside_merchant_quote_is_not_rendered_as_extra_link():
    content = "Free returns. Questions? Visit http://phish.attacker.com/claim now."
    sheet = PromiseSheet.model_validate({
        "seller_domain": SELLER, "sources": [source("a", f"https://{SELLER}/returns", content)],
        "records": [row("returns", "supported_as_statement", [("a", content)], statement="Free returns.")]})
    checked = validate_promise_sheet(sheet, sheet.sources)
    assert checked.records, "fixture row is a valid exact span"
    text = format_sms(base_assessment(promise_sheet=checked))
    allowed = {str(s.url) for s in checked.sources}
    found = set(URL_RE.findall(text))
    assert found <= allowed and len(found) <= 2, found


def test_PROM_10_duplicates_deduplicated_and_missing_provenance_rejected():
    duplicate = [{"url": f"https://{SELLER}/returns", "content": f"{SELLER} returns A"},
                 {"url": f"https://{SELLER}/returns", "content": f"{SELLER} returns B"}]
    body = Harness(search=duplicate).post().json()
    report = body["assessment"]["research"][0]
    assert (report["records_received"], report["records_retained"], report["records_filtered"]) == (2, 1, 1)
    assert body["message_text"].count(f"https://{SELLER}/returns") == 1
    sheet = PromiseSheet.model_validate({
        "seller_domain": SELLER, "sources": [source("a", LISTING, "Free returns.")],
        "records": [row("returns", "supported_as_statement", statement=None),
                    row("returns", "supported_as_statement", [("a", "Free returns.")], statement="Free returns."),
                    row("returns", "supported_as_statement", [("a", "Free returns.")], statement="Free returns.")]})
    assert len(validate_promise_sheet(sheet, sheet.sources).records) == 1
    duplicate_sources = [source("a", LISTING, "Free returns."), source("b", LISTING, "Paid returns.")]
    assert len(validate_promise_sheet(sheet, duplicate_sources).sources) == 1
    for missing in ["url", "retrieved_at", "content"]:
        value = source("a", LISTING, "Free returns.")
        value.pop(missing)
        with pytest.raises(ValidationError):
            PromiseSource.model_validate(value)
    with pytest.raises(ValidationError):
        Evidence.model_validate({k: v for k, v in evidence().model_dump().items() if k != "source_url"})


# ---------------------------------------------------------------- RES

def test_RES_01_five_received_two_retained_three_filtered_partial():
    results = [
        {"url": f"https://{SELLER}/returns", "title": "Returns", "content": "Returns accepted within 30 days."},
        {"url": "https://forum-reviews.com/t/1", "title": "Forum", "content": f"Has anyone bought from {SELLER}?"},
        {"url": "https://other-seller.com/", "title": "Other", "content": "A different perfume store."},
        {"url": "http://10.0.0.8/internal", "title": "Private", "content": f"{SELLER} internal"},
        {"url": "https://empty-content.com/", "title": "Empty", "content": "   "},
    ]
    body = Harness(search=results).post().json()
    assessment = body["assessment"]
    assert assessment["research"] == [{"provider": "tavily", "status": "partial", "provider_called": True,
                                       "records_received": 5, "records_retained": 2, "records_filtered": 3}]
    assert len(assessment["evidence"]) == 2
    assert all(e["claim_status"] == "unknown" and e["evidence_type"] == "search_snippet" for e in assessment["evidence"])
    assert body["message_text"].count("Unverified source:") == 2
    assert assessment["data_mode"] == "partial"


def test_RES_04_search_snippet_cannot_become_merchant_policy():
    class Client:
        calls = 0

        async def complete(self, message, schema):
            Client.calls += 1
            return json.dumps({"records": [row("returns", "supported_as_statement",
                                                [("source_1", f"{SELLER} offers free returns.")],
                                                statement=f"{SELLER} offers free returns.")]})
    snippet = SourceRecord("https://forum-reviews.com/t/1", "SYNTHETIC forum", f"{SELLER} offers free returns.",
                           datetime.now(timezone.utc))
    sheet = asyncio.run(PromiseExtractor(Client(), data_mode="mock").extract(SimpleNamespace(product_url=LISTING), [snippet]))
    assert Client.calls == 1
    assert sheet.sources[0].content_kind == "search_snippet"
    assert not any(r.status == "supported_as_statement" for r in sheet.records)


def test_RES_05_extract_is_bounded_in_urls_size_and_time():
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"{" + b" " * 256_001 + b"}")
    provider = TavilyProvider("qa-synthetic", transport=httpx.MockTransport(handler))
    with pytest.raises(ResearchUnavailable):
        asyncio.run(provider.extract_sources([f"https://{SELLER}/{i}" for i in range(4)]))
    with pytest.raises(ResearchUnavailable):
        asyncio.run(provider.extract_sources([f"https://user:pw@{SELLER}/returns"]))
    assert calls == []
    with pytest.raises(ResearchUnavailable):
        asyncio.run(provider.extract_sources([LISTING]))
    assert len(calls) == 1

    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"results": []})
    with pytest.raises(ResearchUnavailable) as error:
        asyncio.run(TavilyProvider("qa-synthetic", transport=httpx.MockTransport(slow), timeout=0.05).extract_sources([LISTING]))
    assert error.value.reason == "timeout"

    from app.research.promises import collect_promise_sources
    seen = []

    class Provider:
        async def extract_sources(self, urls):
            seen.append(list(urls))
            return []

    async def identity(url):
        return url
    records = [SourceRecord(f"https://{SELLER}/page-{i}", "t", "x", datetime.now(timezone.utc)) for i in range(5)]
    plan = SimpleNamespace(product_url=LISTING, requires_user_input=False)
    asyncio.run(collect_promise_sources(Provider(), plan, records, destination_validator=identity))
    assert len(seen) == 1 and len(seen[0]) == 3 and seen[0][0] == LISTING


@pytest.mark.parametrize("url", [
    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/", "http://100.64.0.1/", "http://0.0.0.0/",
    "http://[fc00::1]/", "http://[fe80::1]/", "http://[::]/", "http://[2001:db8::1]/", "http://[::ffff:127.0.0.1]/",
    "https://user@synthetic-shop.com/", "ftp://synthetic-shop.com/", "http://metadata.google.internal/",
    "http://169.254.169.254/latest/meta-data", "http://017700000001/", "javascript:alert(1)",
])
def test_RES_06_private_credential_and_non_http_targets_rejected(url):
    with pytest.raises(UnsafeURL):
        public_url(url)


def test_RES_06_mixed_ipv6_dns_and_unsafe_listing_skip_provider_retrieval():
    import socket

    async def mixed(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fd00::1", 0, 0, 0))]
    with pytest.raises(UnsafeURL):
        asyncio.run(validate_public_destination(LISTING, mixed))

    async def unsafe(url):
        raise UnsafeURL("QA synthetic private resolution")
    harness = Harness(validator=unsafe)
    body = harness.post().json()
    assert "/search" not in harness.calls and "/extract" not in harness.calls
    assert body["assessment"]["research"][0]["status"] == "unsafe_url"
    assert body["assessment"]["research"][0]["provider_called"] is False
    assert "could not be safely resolved" in body["message_text"]
    assert body["assessment"]["decision"] == "VERIFY_FIRST"


# ---------------------------------------------------------------- DOM / IMG

def test_DOM_01_registration_date_is_dated_context_only():
    body = Harness().post().json()
    context = body["assessment"]["promise_sheet"]["domain_context"]
    assert context["status"] == "context_only"
    assert context["registered_at"].startswith("2019-05-01")
    assert context["source_url"] == f"https://rdap.verisign.com/com/v1/domain/{SELLER}"
    assert context["retrieved_at"]
    assert "not business age" in context["explanation"]
    assert body["assessment"]["decision"] == "VERIFY_FIRST"


@pytest.mark.parametrize("rdap", [
    httpx.Response(404, json={}),
    lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("QA timeout", request=request)),
    {"ldhName": SELLER, "events": [{"eventAction": "registration", "eventDate": "not-a-date"}]},
    {"ldhName": SELLER, "events": [{"eventAction": "registration", "eventDate": "2019-05-01T00:00:00"}]},
    {"ldhName": SELLER, "events": []},
    {"ldhName": SELLER, "events": [{"eventAction": "registration", "eventDate": "2019-05-01T00:00:00Z"},
                                   {"eventAction": "registration", "eventDate": "2020-05-01T00:00:00Z"}]},
], ids=["http_404", "timeout", "invalid_date", "naive_date", "missing", "ambiguous"])
def test_DOM_02_missing_invalid_or_failed_registration_is_unavailable(rdap):
    context = Harness(rdap=rdap).post().json()["assessment"]["promise_sheet"]["domain_context"]
    assert context["status"] == "unavailable" and context["registered_at"] is None


@pytest.mark.parametrize("seller", ["synthetic-shop.org", "shop.synthetic-shop.com", "synthetic-shop.co.uk"])
def test_DOM_02_unsupported_domain_never_widens_endpoint(seller):
    from app.research.domain import DomainLookup
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})
    result = asyncio.run(DomainLookup(transport=httpx.MockTransport(handler)).lookup(seller))
    assert result.status == "unavailable" and calls == []


def test_IMG_01_image_checks_unavailable_and_model_cannot_claim_matches():
    rows = [row("photo_reuse", "independently_corroborated", [("source_1", "Free returns.")], statement="Free returns."),
            row("ai_photo", "supported_as_statement", [("source_1", "AI-photo confidence 12%")], statement="AI-photo confidence 12%")]
    harness = Harness(extract=CONFLICT_EXTRACT, promise={"records": rows})
    body = harness.post().json()
    sheet = body["assessment"]["promise_sheet"]
    assert sheet["image_context"]["status"] == "unavailable"
    assert sheet["image_context"]["source_url"] is None
    assert not any(r["topic"] in {"photo_reuse", "ai_photo"} and r["status"] != "unavailable" for r in sheet["records"])
    assert "%" not in body["message_text"]


# ---------------------------------------------------------------- RISK

@pytest.mark.parametrize("records", [
    [evidence(finding="discount"), evidence(finding="discount", source_url="https://investigator-two.com/r", evidence_type="investigation")],
    [evidence(evidence_type="complaint", claim_status="allegation", source_url="https://complaints-one.com/a"),
     evidence(evidence_type="community", claim_status="allegation", source_url="https://forum-two.com/b")],
    [evidence(evidence_type="unverified_review", source_url="https://reviews-one.com/a"),
     evidence(evidence_type="unverified_review", source_url="https://reviews-two.com/b")],
    [evidence(evidence_type="search_snippet", finding="seller_authorized", source_url="https://brand-directory.com/x"),
     evidence(evidence_type="search_snippet", claim_status="unknown", finding="seller_authorized")],
    [evidence(finding="authorization_unknown", evidence_type="official", source_url="https://brand-directory.com/x")],
    [],
], ids=["discount_only", "allegations_only", "reviews_only", "snippets_claiming_authorization", "authorization_unknown", "unknown_seller"])
def test_RISK_01_weak_signals_yield_verify_first_without_probability(records):
    request, plan = policy_inputs()
    result = decide(request, plan, records)
    assert (result.seller_risk, result.decision) == (Risk.INSUFFICIENT_EVIDENCE, Decision.VERIFY_FIRST)
    text = format_sms(result)
    assert "authenticity is not established" in text
    assert_no_accusation(text + result.summary + " ".join(result.missing_information))


def test_RISK_01_young_domain_context_does_not_change_risk():
    request, plan = policy_inputs()
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    sheet = PromiseSheet(seller_domain=SELLER, domain_context=PromiseContext(
        status="context_only", registered_at=yesterday, retrieved_at=datetime.now(timezone.utc),
        source_url=f"https://rdap.verisign.com/com/v1/domain/{SELLER}", explanation="SYNTHETIC context"))
    with_context, without = decide(request, plan, [], sheet), decide(request, plan, [])
    assert (with_context.seller_risk, with_context.decision) == (without.seller_risk, without.decision)
    conflict = PromiseSheet.model_validate_json((FIXTURES / "promise_conflict.json").read_text())
    assert decide(request, plan, [], conflict).decision == without.decision


def test_RISK_02_lower_risk_wording_never_claims_authenticity():
    request, plan = policy_inputs()
    official = evidence(evidence_type="official", finding="seller_authorized", source_url="https://brand-directory.com/retailers")
    result = decide(request, plan, [official])
    assert result.seller_risk == Risk.LOWER_RISK
    assert "Authorization does not establish product authenticity." in result.missing_information
    text = format_sms(result)
    assert "Product authenticity is not established." in text
    assert_no_accusation(text)


def test_RISK_03_grounded_conflict_stays_explicit_and_conservative():
    request, plan = policy_inputs()
    official = evidence(evidence_type="official", finding="seller_authorized", source_url="https://brand-directory.com/retailers")
    adverse = [evidence(), evidence(source_url="https://investigator-two.com/r", evidence_type="investigation")]
    result = decide(request, plan, [official, *adverse])
    assert result.decision == Decision.VERIFY_FIRST
    assert "conflict" in result.summary.lower()
    assert result.missing_information[0] == "Resolution of conflicting seller evidence"
    single = decide(request, plan, adverse[:1])
    assert single.decision == Decision.VERIFY_FIRST
    assert decide(request, plan, adverse).decision == Decision.AVOID


# ---------------------------------------------------------------- OUT

def test_OUT_01_insufficient_but_relevant_sources_give_useful_summary_and_two_intact_links():
    results = CONFLICT_SEARCH + [{"url": f"https://{SELLER}/page-{i}", "title": f"Page {i}", "content": f"{SELLER} page {i}"}
                                 for i in range(4)]
    harness = Harness(search=results, extract=CONFLICT_EXTRACT, promise={"records": [CONFLICT_ROW]})
    body = harness.post().json()
    assessment, message = body["assessment"], body["message_text"]
    assert assessment["decision"] == "VERIFY_FIRST"
    assert "Verify authorization and return terms" in message
    found = URL_RE.findall(message)
    assert 1 <= len(set(found)) <= 2
    known = {s["url"] for s in assessment["promise_sheet"]["sources"]} | {e["source_url"] for e in assessment["evidence"]}
    assert set(found) <= known
    assert "Potentially differing terms" in message


def test_OUT_02_long_links_repeated_records_and_mock_label_stay_bounded_and_intact():
    long_urls = [f"https://{SELLER}/{'policy-' * 30}{i}" for i in range(3)]
    sources = [source(f"s{i}", url, f"Quote number {i} " + "terms " * 60) for i, url in enumerate(long_urls)]
    rows = [row(topic, "supported_as_statement", [(f"s{i % 3}", f"Quote number {i % 3} " + "terms " * 60)])
            for i, topic in enumerate(["returns", "return_cost", "shipping_origin", "arrival", "processing_time", "transit_time"])]
    sheet = validate_promise_sheet(PromiseSheet.model_validate({"seller_domain": SELLER, "sources": sources, "records": rows}), sources)
    snippets = [evidence(evidence_type="search_snippet", claim_status="unknown", finding="other", polarity="neutral",
                         source_url=url) for url in long_urls * 2]
    assessment = base_assessment(promise_sheet=sheet, evidence=[e.model_dump() for e in snippets])
    for budget in (350, 600, 1000):
        text = format_sms(assessment, budget)
        assert len(text) <= budget
        assert text.startswith("[SYNTHETIC/MOCK]")
        assert set(URL_RE.findall(text)) <= set(long_urls)
        assert text.count('"') % 2 == 0, "quotes must never be cut mid-span"
        assert "authenticity is not established" in text


def test_OUT_02_clarification_reply_bounded_and_labeled():
    body = Harness(settings=Settings()).post().json()
    assert len(body["message_text"]) <= 1000
    assert "[PARTIAL DATA]" in body["message_text"]
    assert body["assessment"]["summary"] in body["message_text"]


def test_OUT_03_fresh_pipelines_give_same_promises_decision_and_uncertainty_per_channel():
    def run(path, headers=None):
        harness = Harness(search=CONFLICT_SEARCH, extract=CONFLICT_EXTRACT, promise={"records": [CONFLICT_ROW]})
        return harness.post(path=path, headers=headers).json()
    extension = run("/api/v1/extension/evaluate", {"Authorization": f"Bearer {TOKEN}"})
    phone = run("/api/v1/evaluate-message")
    ext_a, phone_a = extension["assessment"], phone["assessment"]
    for field in ["seller_risk", "decision", "summary", "missing_information", "research", "data_mode"]:
        assert ext_a[field] == phone_a[field], field
    assert ext_a["promise_sheet"]["records"] == phone_a["promise_sheet"]["records"]
    assert [e["source_url"] for e in ext_a["evidence"]] == [e["source_url"] for e in phone_a["evidence"]]
    assert extension["message_text"] == phone["message_text"]
    assert format_sms(Assessment.model_validate(ext_a)) == extension["message_text"]


@pytest.mark.parametrize("fixture", ["conflict", "supported", "missing", "unavailable", None])
@pytest.mark.parametrize("risk,decision_value", [("LOWER_RISK", "CONSIDER_BUYING"), ("HIGHER_RISK", "AVOID"),
                                                 ("INSUFFICIENT_EVIDENCE", "VERIFY_FIRST"),
                                                 ("INSUFFICIENT_EVIDENCE", "NEED_MORE_INFORMATION")])
@pytest.mark.parametrize("mode", ["mock", "partial"])
def test_OUT_all_formatted_outputs_avoid_accusation_probability_and_keep_labels(fixture, risk, decision_value, mode):
    sheet = None
    if fixture:
        raw = PromiseSheet.model_validate_json((FIXTURES / f"promise_{fixture}.json").read_text())
        sheet = validate_promise_sheet(raw, raw.sources)
    assessment = base_assessment(seller_risk=risk, decision=decision_value, data_mode=mode, promise_sheet=sheet)
    text = format_sms(assessment)
    assert text.startswith("[SYNTHETIC/MOCK]" if mode == "mock" else "[PARTIAL DATA]")
    assert "Product authenticity is not established." in text
    assert_no_accusation(text)
    request, plan = policy_inputs()
    for records in ([], [evidence()], [evidence(), evidence(source_url="https://investigator-two.com/r")]):
        result = decide(request, plan, records)
        assert_no_accusation(" ".join([result.summary, *result.missing_information]))
