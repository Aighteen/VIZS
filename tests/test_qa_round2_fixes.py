"""Fixes for QA round 2 (QA-06, QA-07, QA-08, Q6, Q7, possessive URL). SYNTHETIC data;
mocked transports only; no network, DNS, keys or messages."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decision.rules import registrable_domain
from app.decision.sms import LINK_REMOVED, neutralize_links
from app.main import create_app
from app.models import Risk, ShoppingRequest
from app.services.grok import SYSTEM_PROMPT, GrokExtractor, _provided_urls
from tests.test_qa_acceptance import Harness, live_settings, plan_output
from tests.test_qa_round2 import decide_for, origin_status, phone_for


# ---------------------------------------------------------------- Q6

@pytest.mark.parametrize("host,expected", [
    ("store.myshop.com", "myshop.com"), ("myshop.com", "myshop.com"), ("WWW.MyShop.com.", "myshop.com"),
    ("a.b.store.myshop.co.uk", "myshop.co.uk"), ("shop.example.com.au", "example.com.au"),
    ("x.y.co.jp", "y.co.jp"), ("store.loja.com.br", "loja.com.br"), ("203.0.113.9", "203.0.113.9"),
])
def test_Q6_registrable_domain(host, expected):
    assert registrable_domain(host) == expected


@pytest.mark.parametrize("listing,url", [
    ("https://store.myshop.com/p", "https://myshop.com/authorized"),          # parent registrable domain
    ("https://store.myshop.com/p", "https://about.myshop.com/authorized"),    # sibling subdomain
    ("https://store.myshop.com/p", "https://www.myshop.com/authorized"),
    ("https://a.store.myshop.co.uk/p", "https://myshop.co.uk/authorized"),   # multi-label public suffix
    ("https://store.brand.com/p", "https://brand.com/retailers"),            # accepted trade-off: VERIFY_FIRST
])
def test_Q6_evidence_under_seller_registrable_domain_never_lower_risk(listing, url):
    assessment = decide_for(listing, url)
    assert assessment.seller_risk != Risk.LOWER_RISK
    assert assessment.decision.value == "VERIFY_FIRST"


@pytest.mark.parametrize("listing,url", [
    ("https://store.myshop.com/p", "https://maison-brand.com/retailers"),
    ("https://store.myshop.co.uk/p", "https://other.co.uk/retailers"),  # same public suffix, different site
    ("https://store.myshop.com/p", "https://myshop.com.evil-net.com/retailers"),
    ("https://store.myshop.com/p", "https://notmyshop.com/retailers"),
])
def test_Q6_unrelated_manufacturer_domain_still_supports_lower_risk(listing, url):
    assert decide_for(listing, url).seller_risk == Risk.LOWER_RISK


# ---------------------------------------------------------------- Q7

MOCK = "/api/v1/mock/messages"
EVENT = json.dumps({"event_id": "qa-r2-fix", "text": "Check https://synthetic-shop.com/p"})


def test_Q7_mock_route_still_404_when_disabled_even_with_origin_or_bad_type():
    with TestClient(create_app(settings=Settings())) as client:
        assert client.post(MOCK, content=EVENT, headers={"Origin": "https://hostile-page.com"}).status_code == 404
        assert client.post(MOCK, content=EVENT, headers={"Content-Type": "text/plain"}).status_code == 404
        assert client.post(MOCK, content=b"x" * 20000).status_code == 404


@pytest.mark.parametrize("origin", ["null", "", "https://hostile-page.com", "http://127.0.0.1:8000"])
def test_Q7_mock_route_rejects_any_origin_with_zero_provider_calls(origin):
    harness = Harness(settings=live_settings(enable_mock_sms=True))
    with TestClient(harness.app()) as client:
        response = client.post(MOCK, content=EVENT, headers={"Origin": origin, "Content-Type": "application/json"})
    assert response.status_code == 403
    assert harness.calls == [] and harness.dns == []


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data",
                                          "application/json-patch+json", ""])
def test_Q7_mock_route_requires_json(content_type):
    harness = Harness(settings=live_settings(enable_mock_sms=True))
    headers = {"Content-Type": content_type} if content_type else {}
    with TestClient(harness.app()) as client:
        assert client.post(MOCK, content=EVENT, headers=headers).status_code == 415
    assert harness.calls == []


def _chunks(total, size=4096):
    sent = 0
    while sent < total:
        yield b"a" * min(size, total - sent)
        sent += size


def test_Q7_mock_route_checks_precede_reading_the_body():
    harness = Harness(settings=live_settings(enable_mock_sms=True))
    with TestClient(harness.app()) as client:
        big = b"x" * 20000
        assert client.post(MOCK, content=big, headers={"Content-Type": "text/plain"}).status_code == 413
        assert client.post(MOCK, content=big, headers={"Origin": "https://hostile-page.com"}).status_code == 403
        assert client.post(MOCK, content=_chunks(40000), headers={"Content-Type": "text/plain"}).status_code == 415
        assert client.post(MOCK, content=_chunks(40000), headers={"Content-Type": "application/json"}).status_code == 413
    assert harness.calls == []


def test_Q7_mock_route_json_without_origin_still_works():
    app = create_app(settings=Settings(enable_mock_sms=True))
    with TestClient(app) as client:
        response = client.post(MOCK, content=EVENT, headers={"Content-Type": "application/json"})
        assert response.status_code == 202 and response.json()["scheduled"] is True


# ---------------------------------------------------------------- QA-06 / Q8

@pytest.mark.parametrize("quote", ["ORIGIN: Paris, France.", "Ships  from New Jersey.", "WAREHOUSE in Ohio.",
                                   "Country of origin: France.", "Items are sent from Lyon."])
def test_QA06_whole_word_origin_wording_any_case_is_retained(quote):
    assert origin_status(quote) == ["supported_as_statement"]


@pytest.mark.parametrize("quote", ["Originally founded at 100 Pike Street, Seattle.", "Warehoused goods: 100 Pike Street.",
                                   "Represent from 100 Pike Street, Seattle."])
def test_QA06_origin_wording_inside_other_words_does_not_count(quote):
    assert origin_status(quote) == ["not_disclosed"]


def test_Q8_word_level_warehouse_in_unrelated_sentence_is_accepted():
    assert origin_status("100 Pike Street, Seattle. Returns go to our warehouse.") == ["supported_as_statement"]


# ---------------------------------------------------------------- QA-08

@pytest.mark.parametrize("text", ["2-3 days.Free returns", "Dr.Smith approved", "Chanel No.5 only", "Costs $89.99.",
                                  "e.g. unopened", "U.S. only", "Ships in 2.5 days.", "Mr.Jones and St.Louis"])
def test_QA08_prose_without_real_tld_survives(text):
    assert neutralize_links(text) == text


@pytest.mark.parametrize("text", [
    "phish-аttacker.com", "phish.рф", "пример.com", "xn--80ak6aa92e.com", "phish.xn--p1ai", "phish。com",
    "phish．com/claim", "phish.shop", "PHISH.STORE", "phish.io/x", "phish.co", "phish.online", "phish.xyz",
    "phish.ly", "203.0.113.9/claim", "203.0.113.9:8080", "tel:+12065550147", "mailto:x@phish.com",
    "days.Free/phish.com",
])
def test_QA08_real_tld_idn_ip_and_tel_are_neutralized(text):
    result = neutralize_links(f"Visit {text} now.")
    assert "phish" not in result.lower().replace("[link removed]", "")
    assert "203.0.113" not in result and "+1206" not in result
    assert LINK_REMOVED in result


def test_QA08_accepted_residual_false_positive_real_cctld_in_prose():
    """Documented residual: a real ccTLD suffix in prose is still replaced (safety wins)."""
    assert neutralize_links("Model No.5 Haus.de Edition") == f"Model No.5 {LINK_REMOVED} Edition"


def test_QA08_prose_survives_in_phone_reply():
    text = phone_for("Free returns in 2-3 days.Free return label from Dr.Smith.")
    assert "2-3 days.Free return label from Dr.Smith." in text


# ---------------------------------------------------------------- QA-07 / possessive

@pytest.mark.parametrize("href", ["https://synthetic-shop.com/p.", "https://synthetic-shop.com/p?",
                                  "https://synthetic-shop.com/p!", "https://synthetic-shop.com/p;",
                                  "https://synthetic-shop.com/p:", "https://synthetic-shop.com/p_(x))",
                                  "https://synthetic-shop.com/it's-50ml'", "https://synthetic-shop.com/p,"])
def test_QA07_angle_brackets_are_an_exact_boundary(href):
    assert _provided_urls(f"Check this listing <{href}>") == {href}
    assert _provided_urls(f"Check this listing <{href}> price $5") == {href}


def test_QA07_prose_rule_unchanged_without_brackets():
    assert _provided_urls("Check https://synthetic-shop.com/p.") == {"https://synthetic-shop.com/p"}
    assert _provided_urls("Is https://synthetic-shop.com/p?") == {"https://synthetic-shop.com/p"}


@pytest.mark.parametrize("message,expected", [
    ("Is https://shop.com's listing ok?", "https://shop.com/"),
    ("Is https://shop.com:8443's listing ok?", "https://shop.com:8443/"),
    ("Check https://shop.com/it's-50ml", "https://shop.com/it's-50ml"),
])
def test_possessive_after_host_is_not_part_of_the_url(message, expected):
    assert _provided_urls(message) == {expected}


def test_QA07_prompt_requires_exact_bracketed_url():
    assert "literally present" in SYSTEM_PROMPT and "angle brackets" in SYSTEM_PROMPT


class _Fake:
    def __init__(self, url):
        self.url = url

    async def complete(self, message, schema):
        return json.dumps(plan_output(product_url=self.url))


@pytest.mark.parametrize("returned,ok", [("https://synthetic-shop.com/p?", True), ("https://synthetic-shop.com/p", False)])
def test_QA07_model_url_must_equal_the_user_supplied_bracketed_url(returned, ok):
    request = ShoppingRequest(request_id="r", message_text="Check this listing <https://synthetic-shop.com/p?>")
    plan = asyncio.run(GrokExtractor(_Fake(returned), data_mode="mock").extract(request))
    assert (plan.intent == "evaluate_purchase" and str(plan.product_url) == "https://synthetic-shop.com/p?") is ok
