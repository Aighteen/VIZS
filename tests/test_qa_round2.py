"""QA round 2: independent, adversarial verification of the QA-01..04 fixes and the
Q1/Q2/Q4 decisions (fix/qa-findings, merged at 6d9e512). SYNTHETIC data; mocked
transports only; no network, DNS, keys or messages.

Strict xfails mark newly confirmed defects (QA-05+, see docs/QA_REPORT.md round 2)."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decision import decide, format_sms, validate_promise_sheet
from app.models import OrchestratorPlan, PromiseSheet, Risk, ShoppingRequest
from app.services.grok import _provided_urls
from tests.test_qa_acceptance import (LISTING, SELLER, TOKEN, URL_RE, XAI_KEY, Harness, base_assessment, chat,
                                      evidence, live_settings, row, source)

ALLOWED_ORIGIN = "chrome-extension://" + "a" * 32
PAYLOAD = {"request_id": "qa-r2", "message_text": f"Check {LISTING}", "channel": "debug"}
BODY = json.dumps(PAYLOAD)
LOCAL_ROUTES = ["/api/v1/evaluate", "/api/v1/evaluate-message"]


def official(url, seller=SELLER):
    return evidence(evidence_type="official", finding="seller_authorized", source_url=url, seller_domain=seller)


def decide_for(listing, url):
    request = ShoppingRequest(request_id="qa-r2", message_text=listing)
    plan = OrchestratorPlan(request_id="qa-r2", intent="evaluate_purchase", product_url=listing, data_mode="mock")
    seller = httpx.URL(listing).host.removeprefix("www.")
    return decide(request, plan, [official(url, seller)])


# ---------------------------------------------------------------- QA-01

@pytest.mark.parametrize("url", [
    f"https://{SELLER}/about", f"https://www.{SELLER}/about", f"https://shop.{SELLER}/authorized",
    f"https://a.b.{SELLER}/x", f"https://{SELLER.upper()}/x", f"https://{SELLER}./about", f"https://WWW.{SELLER.upper()}/x",
])
def test_QA01_seller_hosted_official_evidence_never_lower_risk(url):
    assert decide_for(LISTING, url).seller_risk != Risk.LOWER_RISK


@pytest.mark.parametrize("url", [
    "https://maison-synthetic-brand.com/retailers",
    f"https://{SELLER}.evil-net.com/retailers",      # lookalike: different site, label is trusted upstream
    f"https://evil-{SELLER}/retailers",               # suffix collision must not be treated as same site
    f"https://not{SELLER}/retailers",
])
def test_QA01_independent_official_domain_can_still_support_lower_risk(url):
    assert decide_for(LISTING, url).seller_risk == Risk.LOWER_RISK


def test_QA01_www_listing_and_bare_seller_evidence_are_same_site():
    assert decide_for(f"https://www.{SELLER}/p", f"https://{SELLER}/about").seller_risk != Risk.LOWER_RISK


# ---------------------------------------------------------------- QA-02

def phone_for(content, conditions=None):
    sheet = PromiseSheet.model_validate({
        "seller_domain": SELLER, "sources": [source("a", f"https://{SELLER}/returns", content)],
        "records": [row("returns", "supported_as_statement", [("a", content)], statement=None, **(conditions or {}))]})
    checked = validate_promise_sheet(sheet, sheet.sources)
    assert checked.records, "fixture row must be a valid span"
    return format_sms(base_assessment(promise_sheet=checked))


@pytest.mark.parametrize("injected", [
    "http://phish.attacker.com/claim", "HTTP://PHISH.ATTACKER.COM", "https://phish.attacker.com:8443/x?y=1#z",
    "www.phish-attacker.com", "WWW.Phish-Attacker.co.uk/claim", "phish-attacker.com", "phish-attacker.com/claim?x=1",
    "sub.phish-attacker.io", "xn--phsh-attacker-q9b.com", "support@phish-attacker.com", "mailto://x@phish-attacker.com",
    "(phish-attacker.com)", "phish-attacker.com.", "javascript://phish-attacker.com/%0aalert(1)",
])
def test_QA02_phone_reply_contains_only_labeled_source_links(injected):
    text = phone_for(f"Free returns. Visit {injected} for details.")
    assert "attacker" not in text.lower().replace("[link removed]", "")
    assert set(URL_RE.findall(text)) <= {f"https://{SELLER}/returns"}
    assert '"Free returns. Visit ' in text and "[link removed]" in text and "for details." in text


def test_QA02_conditions_are_neutralized_too():
    content = "Free returns for orders via phish-attacker.com within 30 days."
    text = phone_for(content, {"region": "orders via phish-attacker.com"})
    assert "phish-attacker" not in text


def test_QA02_choice_b_merchant_own_domain_text_inside_quote_is_replaced():
    """Fixer choice (b), pending human decision: the merchant's own domain written in a
    quote is also replaced; the labeled source URL itself stays intact and tappable."""
    text = phone_for(f"Free returns. Ship items back via {SELLER}/returns-portal within 30 days.")
    assert f"via [link removed] within 30 days" in text
    assert f"https://{SELLER}/returns" in text
    assert text.count(f"{SELLER}") == 1  # only the appended labeled source link


@pytest.mark.parametrize("injected", ["phish-аttacker.com/claim", "phish.рф/claim", "пример.com"],
                         ids=["idn_homoglyph", "unicode_tld", "cyrillic_label"])
def test_QA02_internationalized_bare_domains_are_neutralized(injected):
    text = phone_for(f"Free returns. Visit {injected} now.")
    assert injected not in text
    assert "Free returns. Visit [link removed]" in text


# ---------------------------------------------------------------- QA-03

@pytest.mark.parametrize("message,expected", [
    ("Check (https://synthetic-shop.com/p).", "https://synthetic-shop.com/p"),
    ("Check https://synthetic-shop.com/p).", "https://synthetic-shop.com/p"),
    ("Is https://synthetic-shop.com/Product_(100ml)?", "https://synthetic-shop.com/Product_(100ml)"),
    ("Is https://synthetic-shop.com/a_(b)_(c) ok", "https://synthetic-shop.com/a_(b)_(c)"),
    ('Check "https://synthetic-shop.com/p".', "https://synthetic-shop.com/p"),
    ("Check https://synthetic-shop.com/p.\nThanks", "https://synthetic-shop.com/p"),
    ("Check this listing https://synthetic-shop.com/product. price $20", "https://synthetic-shop.com/product."),
])
def test_QA03_documented_trim_rule_holds_for_adversarial_prose(message, expected):
    assert _provided_urls(message) == {expected}


def test_QA03_seller_subdomain_vs_lookalike_are_distinct_urls():
    assert len(_provided_urls(f"Compare https://{SELLER}.evil.net/p and https://{SELLER}/p")) == 2


# Exact message_text strings extension/src/lib/request.js builds (checked on the node side
# in extension/test/qa-round2.test.js). The listing href is the tab URL as Chrome reports it.
EXTENSION_END_PUNCTUATION = [
    ("https://synthetic-shop.com/product.", None),
    ("https://synthetic-shop.com/p?", None),
    ("https://synthetic-shop.com/p?", "$20"),
    ("https://synthetic-shop.com/sale!", None),
    ("https://synthetic-shop.com/a;b;", None),
    ("https://synthetic-shop.com/p:", None),
    ("https://synthetic-shop.com/p?q=1)", "$5"),
]


def extension_message(href, price):
    # QA-07 fix: the extension now wraps the tab href in angle brackets.
    return f"Check this listing <{href}>" + (f" price {price}" if price else "")


@pytest.mark.parametrize("href,price", EXTENSION_END_PUNCTUATION, ids=lambda v: str(v))
def test_QA03_backend_extracts_exact_extension_href_with_trailing_punctuation(href, price):
    assert _provided_urls(extension_message(href, price)) == {href}


# ---------------------------------------------------------------- Q1

def live_app(**settings):
    harness = Harness(settings=live_settings(**settings))
    return harness, harness.app()


@pytest.mark.parametrize("path", LOCAL_ROUTES)
@pytest.mark.parametrize("origin", ["null", "", "https://hostile-page.com", ALLOWED_ORIGIN, "http://127.0.0.1:8000"])
def test_Q1_any_origin_rejected_on_local_routes_with_zero_provider_calls(path, origin):
    harness, app = live_app(extension_origins=(ALLOWED_ORIGIN,))
    with TestClient(app) as client:
        response = client.post(path, content=BODY, headers={"Origin": origin, "Content-Type": "application/json"})
    assert response.status_code == 403
    assert harness.calls == [] and harness.dns == []


@pytest.mark.parametrize("path", LOCAL_ROUTES)
@pytest.mark.parametrize("content_type,expected", [
    ("Application/JSON", 200), ("application/json; charset=UTF-8", 200), ("APPLICATION/JSON ; charset=utf-8", 200),
    ("application/json-patch+json", 415), ("application/merge-patch+json", 415), ("application/json, text/plain", 415),
    ("text/json", 415), ("application/x-json", 415), ("text/plain; application/json", 415), ("", 415),
])
def test_Q1_content_type_matching_is_exact_media_type(path, content_type, expected):
    harness, app = live_app()
    headers = {"Content-Type": content_type} if content_type else {}
    with TestClient(app) as client:
        response = client.post(path, content=BODY, headers=headers)
    assert response.status_code == expected
    if expected != 200:
        assert harness.calls == []


def _chunks(total, size=4096):
    sent = 0
    while sent < total:
        yield b"a" * min(size, total - sent)
        sent += size


@pytest.mark.parametrize("path", LOCAL_ROUTES)
def test_Q1_origin_and_media_checks_precede_reading_a_chunked_oversized_body(path):
    harness, app = live_app()
    with TestClient(app) as client:
        assert client.post(path, content=_chunks(40000), headers={"Origin": "https://hostile-page.com"}).status_code == 403
        assert client.post(path, content=_chunks(40000), headers={"Content-Type": "text/plain"}).status_code == 415
        assert client.post(path, content=_chunks(40000), headers={"Content-Type": "application/json"}).status_code == 413
    assert harness.calls == []


@pytest.mark.parametrize("path", LOCAL_ROUTES + ["/api/v1/extension/evaluate"])
def test_Q1_choice_a_declared_oversize_returns_413_before_415(path):
    harness, app = live_app(extension_origins=(ALLOWED_ORIGIN,))
    auth = {"Authorization": f"Bearer {TOKEN}"} if "extension" in path else {}
    with TestClient(app) as client:
        big = b"x" * 20000
        assert client.post(path, content=big, headers={**auth, "Content-Type": "text/plain"}).status_code == 413
        assert client.post(path, content=big, headers={**auth}).status_code == 413
        if "extension" not in path:
            assert client.post(path, content=big, headers={"Origin": "https://hostile-page.com"}).status_code == 403
    assert harness.calls == []


def test_Q1_extension_route_requires_json_but_not_blanket_origin_rule_and_415_costs_no_budget():
    harness = Harness(settings=live_settings(extension_origins=(ALLOWED_ORIGIN,), extension_requests_per_minute=1))
    headers = {"Authorization": f"Bearer {TOKEN}", "Origin": ALLOWED_ORIGIN}
    with TestClient(harness.app()) as client:
        for content_type in ["text/plain", "application/x-www-form-urlencoded", "application/json-patch+json"]:
            assert client.post("/api/v1/extension/evaluate", content=BODY,
                               headers={**headers, "Content-Type": content_type}).status_code == 415
        assert harness.calls == []
        ok = client.post("/api/v1/extension/evaluate", content=BODY, headers={**headers, "Content-Type": "application/json"})
        assert ok.status_code == 200, "415 rejections must not consume the 1/minute budget"
        assert client.post("/api/v1/extension/evaluate", content=BODY,
                           headers={"Authorization": "Bearer wrong", "Content-Type": "text/plain"}).status_code == 401


def test_Q1_extension_client_request_shape_is_accepted():
    """Headers exactly as extension/src/lib/request.js sends them (node side asserts the same)."""
    harness = Harness(settings=live_settings(extension_origins=(ALLOWED_ORIGIN,)))
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}", "Origin": ALLOWED_ORIGIN}
    body = json.dumps({"request_id": "r", "message_text": f"Check this listing {LISTING} price $89.99", "channel": "debug"})
    with TestClient(harness.app()) as client:
        assert client.post("/api/v1/extension/evaluate", content=body, headers=headers).status_code == 200


def test_Q1_bridge_request_shape_is_accepted():
    """Node fetch (test-bridge.mjs) sends JSON and no Origin header (verified with a loopback probe)."""
    harness = Harness()
    with TestClient(harness.app()) as client:
        assert client.post("/api/v1/evaluate-message", content=BODY, headers={"Content-Type": "application/json"}).status_code == 200


# ---------------------------------------------------------------- Q2

@pytest.mark.parametrize("plan", [
    lambda r: httpx.Response(500, text="x"),
    lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("t", request=r)),
    lambda r: chat("not json"),
], ids=["unavailable", "timeout", "invalid_output"])
@pytest.mark.parametrize("path", ["/api/v1/evaluate-message", "/api/v1/extension/evaluate"])
def test_Q2_extraction_failure_with_url_never_asks_to_resend(plan, path):
    harness = Harness(plan=plan)
    headers = {"Authorization": f"Bearer {TOKEN}"} if "extension" in path else {}
    body = harness.post(path=path, headers=headers).json()
    message = body["message_text"].lower()
    assert "send the product listing url" not in message and "resend" not in message
    assert "try again later" in message
    assert body["assessment"]["decision"] == "NEED_MORE_INFORMATION"
    assert XAI_KEY not in json.dumps(body)


@pytest.mark.parametrize("text", ["Is this seller ok?", f"{LISTING} or https://other-seller.com/p"])
def test_Q2_missing_or_ambiguous_url_still_asks_for_one(text):
    body = Harness().post(text=text).json()
    assert "listing url" in body["message_text"].lower()


def test_Q2_offline_mode_with_url_says_try_later():
    body = Harness(settings=Settings()).post().json()
    assert "send the product listing url" not in body["message_text"].lower()
    assert "try again later" in body["message_text"].lower()


# ---------------------------------------------------------------- Q4

def origin_status(quote):
    content = quote + " Free returns within 30 days."
    sheet = PromiseSheet.model_validate({"seller_domain": SELLER, "sources": [source("a", LISTING, content)],
                                         "records": [row("shipping_origin", "supported_as_statement", [("a", quote)])]})
    return [r.status for r in validate_promise_sheet(sheet, sheet.sources).records]


@pytest.mark.parametrize("quote", ["Synthetic Product LLC, 100 Pike Street, Seattle, WA 98101.",
                                   "Visit our Seattle boutique.", "Made in France.", "Based in New Jersey since 1999."])
def test_Q4_address_or_location_without_origin_wording_is_not_disclosed(quote):
    assert origin_status(quote) == ["not_disclosed"]


@pytest.mark.parametrize("quote", ["All orders ship from our New Jersey warehouse.", "Dispatched from Paris within 2 days.",
                                   "Fulfilled from our Ohio fulfillment center."])
def test_Q4_explicit_origin_wording_is_retained(quote):
    assert origin_status(quote) == ["supported_as_statement"]


@pytest.mark.parametrize("quote", ["Original packaging only. 100 Pike Street, Seattle, WA.",
                                   "With your consent from checkout we bill 100 Pike Street, Seattle.",
                                   "Aboriginal art prints. 100 Pike Street, Seattle."],
                         ids=["original", "consent_from", "aboriginal"])
def test_Q4_origin_wording_must_be_whole_words(quote):
    assert origin_status(quote) == ["not_disclosed"]


def test_Q4_downgraded_origin_reaches_phone_as_not_disclosed_without_address():
    quote = "Synthetic Product LLC, 100 Pike Street, Seattle, WA 98101."
    sheet = PromiseSheet.model_validate({"seller_domain": SELLER, "sources": [source("a", LISTING, quote)],
                                         "records": [row("shipping_origin", "supported_as_statement", [("a", quote)], statement=quote)]})
    text = format_sms(base_assessment(promise_sheet=validate_promise_sheet(sheet, sheet.sources)))
    assert "shipping origin: not disclosed in inspected source" in text
    assert "Pike Street" not in text
