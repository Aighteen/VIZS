"""Regression tests for QA-01..03 and tech-lead decisions Q1, Q2, Q4.

SYNTHETIC data and mocked transports only; no live calls, keys or DNS.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decision import decide, format_sms, validate_promise_sheet
from app.decision.promises import ORIGIN_NOT_PROVEN
from app.main import create_app
from app.models import Assessment, Evidence, OrchestratorPlan, PromiseSheet, Risk, ShoppingRequest
from app.services.grok import _provided_urls
from tests.test_qa_acceptance import SELLER, URL_RE, base_assessment, row, source

LISTING = f"https://{SELLER}/product/qa"
PAYLOAD = {"request_id": "qa-fix", "message_text": f"Check {LISTING}", "channel": "debug"}
TOKEN = "qa-synthetic-pairing-token"
ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
NOW = "2026-10-17T12:00:00Z"


# ---------------------------------------------------------------- Q1 local route guard

def counting_app(**settings):
    calls = []

    def grok(request):
        calls.append("grok")
        return httpx.Response(503)

    app = create_app(settings=Settings(provider_mode="live", xai_api_key="synthetic", xai_model="synthetic",
                                       extension_token=TOKEN, extension_origins=(ORIGIN,), **settings),
                     xai_transport=httpx.MockTransport(grok), tavily_transport=httpx.MockTransport(grok),
                     domain_transport=httpx.MockTransport(grok))
    return app, calls


@pytest.mark.parametrize("path", ["/api/v1/evaluate", "/api/v1/evaluate-message"])
@pytest.mark.parametrize("origin", ["https://evil.example", "null", ORIGIN])
def test_Q1_local_routes_reject_any_origin_before_evaluation(path, origin):
    app, calls = counting_app()
    with TestClient(app) as client:
        response = client.post(path, json=PAYLOAD, headers={"Origin": origin})
        assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize("path", ["/api/v1/evaluate", "/api/v1/evaluate-message"])
@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded",
                                          "multipart/form-data; boundary=x", "application/jsonx"])
def test_Q1_local_routes_require_json_content_type(path, content_type):
    app, calls = counting_app()
    headers = {"Content-Type": content_type} if content_type else {}
    with TestClient(app) as client:
        response = client.post(path, content=json.dumps(PAYLOAD), headers=headers)
        assert response.status_code == 415
    assert calls == []


@pytest.mark.parametrize("path", ["/api/v1/evaluate", "/api/v1/evaluate-message"])
def test_Q1_local_routes_accept_bridge_style_json_without_origin(path):
    with TestClient(create_app(settings=Settings())) as client:
        response = client.post(path, content=json.dumps(PAYLOAD),
                               headers={"Content-Type": "application/json; charset=utf-8"})
        assert response.status_code == 200


def test_Q1_extension_route_keeps_origin_and_pairing_but_requires_json():
    app, calls = counting_app()
    auth = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app) as client:
        assert client.post("/api/v1/extension/evaluate", content=json.dumps(PAYLOAD),
                           headers={**auth, "Origin": ORIGIN, "Content-Type": "text/plain"}).status_code == 415
        assert client.post("/api/v1/extension/evaluate", json=PAYLOAD,
                           headers={**auth, "Origin": "https://evil.example"}).status_code == 403
        assert client.post("/api/v1/extension/evaluate", json=PAYLOAD, headers={"Origin": ORIGIN}).status_code == 401
        assert calls == []
        response = client.post("/api/v1/extension/evaluate", json=PAYLOAD, headers={**auth, "Origin": ORIGIN})
        assert response.status_code == 200
        assert set(response.json()) == {"assessment", "message_text"}


# ---------------------------------------------------------------- Q2 extraction failure reply

def grok_app(behavior):
    def grok(request):
        if behavior == "timeout":
            raise httpx.ReadTimeout("private")
        if behavior == "invalid":
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "bad"}}]})
        return httpx.Response(503, text="private")
    return create_app(settings=Settings(provider_mode="live", xai_api_key="synthetic", xai_model="synthetic"),
                      xai_transport=httpx.MockTransport(grok), tavily_transport=httpx.MockTransport(grok))


@pytest.mark.parametrize("make_app", [lambda: create_app(settings=Settings()), lambda: grok_app("timeout"),
                                      lambda: grok_app("invalid"), lambda: grok_app("http_error")],
                         ids=["offline_unavailable", "timeout", "invalid_output", "http_error"])
def test_Q2_extraction_failure_with_url_says_try_later_not_send_url(make_app):
    with TestClient(make_app()) as client:
        body = client.post("/api/v1/evaluate-message", json=PAYLOAD).json()
    text = body["message_text"]
    assert body["assessment"]["decision"] == "NEED_MORE_INFORMATION"
    assert "could not be completed" in text and "try again later" in text
    assert "Send the product listing URL" not in text
    assert "listing URL" not in text and "resend" not in text.lower()
    assert len(text) <= 1000


def test_Q2_no_url_still_asks_for_url():
    with TestClient(create_app(settings=Settings())) as client:
        body = client.post("/api/v1/evaluate-message",
                           json={**PAYLOAD, "message_text": "Is this product legit?"}).json()
    text = body["message_text"]
    assert body["assessment"]["decision"] == "NEED_MORE_INFORMATION"
    assert "listing URL" in text
    assert "could not be completed" not in text


def test_Q2_formatter_asks_for_url_only_when_url_is_missing():
    asking = base_assessment(decision="NEED_MORE_INFORMATION", summary="Send the product listing URL.",
                             missing_information=["Product listing URL and context"])
    failed = base_assessment(decision="NEED_MORE_INFORMATION", summary="Shopping extraction timed out.",
                             missing_information=["Shopping extraction timed out."])
    assert "Send the product listing URL" in format_sms(asking)
    assert "could not be completed" in format_sms(failed)
    assert "Send the product listing URL" not in format_sms(failed)


# ---------------------------------------------------------------- Q4 shipping origin

@pytest.mark.parametrize("quote", ["100 Pike Street, Seattle, WA", "Contact us at our Seattle office.",
                                   "Located at 1 Main St, Austin TX"])
def test_Q4_address_is_not_shipping_origin(quote):
    content = f"About us. {quote} Free returns."
    sheet = PromiseSheet.model_validate({
        "seller_domain": SELLER, "sources": [source("a", LISTING, content)],
        "records": [row("shipping_origin", "supported_as_statement", [("a", quote)], statement=quote)]})
    [checked] = validate_promise_sheet(sheet, sheet.sources).records
    assert checked.status == "not_disclosed" and checked.quotes == []
    assert checked.merchant_statement is None
    assert checked.explanation == ORIGIN_NOT_PROVEN
    assert "address is not proof of shipping origin" in checked.explanation
    text = format_sms(base_assessment(promise_sheet=validate_promise_sheet(sheet, sheet.sources)))
    assert quote not in text and "shipping origin: not disclosed" in text


@pytest.mark.parametrize("quote", ["Orders ship from our New Jersey warehouse.", "SHIPPED FROM Paris, France",
                                   "Dispatched from the EU.", "All orders are fulfilled from Ohio.",
                                   "Sent from our fulfillment center in Reno.", "Country of origin: France"])
def test_Q4_explicit_origin_wording_is_kept(quote):
    sheet = PromiseSheet.model_validate({
        "seller_domain": SELLER, "sources": [source("a", LISTING, f"Shipping. {quote}")],
        "records": [row("shipping_origin", "supported_as_statement", [("a", quote)], statement=quote)]})
    [checked] = validate_promise_sheet(sheet, sheet.sources).records
    assert checked.status == "supported_as_statement"


def test_Q4_corroborated_address_also_downgraded_and_other_topics_untouched():
    address = "100 Pike Street, Seattle, WA"
    returns = "Returns accepted within 30 days."
    sources = [source("a", LISTING, f"{address}. {returns}"), source("b", "https://independent-review.com/x", address, kind="independent_page")]
    sheet = PromiseSheet.model_validate({"seller_domain": SELLER, "sources": sources, "records": [
        row("shipping_origin", "independently_corroborated", [("a", address), ("b", address)]),
        row("returns", "supported_as_statement", [("a", returns)])]})
    records = {r.topic: r for r in validate_promise_sheet(sheet, sources).records}
    assert records["shipping_origin"].status == "not_disclosed"
    assert records["returns"].status == "supported_as_statement"


# ---------------------------------------------------------------- QA-01/02/03 extra coverage

def test_QA01_manufacturer_domain_still_supports_lower_risk_but_seller_subdomain_does_not():
    request = ShoppingRequest(request_id="qa", message_text=LISTING)
    plan = OrchestratorPlan(request_id="qa", intent="evaluate_purchase", product_url=LISTING, data_mode="mock")

    def ev(url):
        return Evidence.model_validate(dict(claim="Authorized retailer list", source_url=url, evidence_type="official",
                                            claim_status="verified_fact", retrieved_at=NOW, excerpt="Authorized",
                                            seller_domain=SELLER, finding="seller_authorized", polarity="supports",
                                            data_mode="mock"))
    assert decide(request, plan, [ev("https://maison-synthetic.com/retailers")]).seller_risk == Risk.LOWER_RISK
    for url in [f"https://www.{SELLER}/about", f"https://about.{SELLER}/authorized", f"https://{SELLER.upper()}/x"]:
        assert decide(request, plan, [ev(url)]).seller_risk != Risk.LOWER_RISK, url


@pytest.mark.parametrize("injected", ["www.phish-attacker.com/claim", "phish-attacker.com/claim",
                                      "HTTPS://PHISH.ATTACKER.COM", "ftp://phish.attacker.com/x"])
def test_QA02_link_like_text_in_quotes_and_conditions_is_neutralized(injected):
    content = f"Free returns. Visit {injected} now. US only via {injected}"
    sheet = PromiseSheet.model_validate({
        "seller_domain": SELLER, "sources": [source("a", f"https://{SELLER}/returns", content)],
        "records": [row("returns", "supported_as_statement", [("a", content)], statement="Free returns.")]})
    text = format_sms(base_assessment(promise_sheet=validate_promise_sheet(sheet, sheet.sources)))
    assert "attacker" not in text.lower()
    assert "Free returns. Visit [link removed] now." in text
    assert set(URL_RE.findall(text)) <= {f"https://{SELLER}/returns"}


@pytest.mark.parametrize("message,expected", [
    ("Check https://x-shop.com/p.", "https://x-shop.com/p"),
    ("Check https://x-shop.com/p. Is it legit?", "https://x-shop.com/p"),
    ("Check https://x-shop.com/p, thanks", "https://x-shop.com/p"),
    ("(see https://x-shop.com/p)", "https://x-shop.com/p"),
    ("Is https://en.x-shop.com/wiki/Product_(100ml) legit?", "https://en.x-shop.com/wiki/Product_(100ml)"),
    ("Is https://en.x-shop.com/wiki/Product_(100ml). ok", "https://en.x-shop.com/wiki/Product_(100ml)."),
    ("Check 'https://x-shop.com/p'", "https://x-shop.com/p"),
    ("Check https://x-shop.com/it's-50ml!", "https://x-shop.com/it's-50ml"),
])
def test_QA03_url_punctuation_rule(message, expected):
    assert _provided_urls(message) == {expected}
