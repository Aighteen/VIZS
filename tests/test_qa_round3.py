"""QA round 3: adversarial verification of the round-2 fixes (Q6 registrable domain, Q7 mock
route lockdown, QA-06 whole-word origin wording, QA-08 link neutralizing, QA-07 bracketed
extension URL, possessive URL fix). SYNTHETIC data; mocked transports; no network or DNS.

Accepted residuals are not re-reported (tech lead, round 3): "Eau.de"-style ccTLD prose
replaced; word-level "warehouse"; small public-suffix list; unassigned 2-letter codes."""
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decision import decide, format_sms, validate_promise_sheet
from app.decision.rules import registrable_domain
from app.decision.sms import LINK_REMOVED, neutralize_links
from app.models import OrchestratorPlan, PromiseSheet, Risk, ShoppingRequest
from app.services.grok import _provided_urls
from tests.test_qa_acceptance import (LISTING, SELLER, URL_RE, Harness, base_assessment, evidence, live_settings,
                                      plan_output, row, source)


def decide_for(listing, *records):
    request = ShoppingRequest(request_id="qa-r3", message_text=listing)
    plan = OrchestratorPlan(request_id="qa-r3", intent="evaluate_purchase", product_url=listing, data_mode="mock")
    return decide(request, plan, list(records))


def official(url, listing):
    return evidence(evidence_type="official", finding="seller_authorized", source_url=url,
                    seller_domain=httpx.URL(listing).host.removeprefix("www."))


# ---------------------------------------------------------------- Q6 registrable domain

@pytest.mark.parametrize("host,expected", [
    ("store.myshop.co.uk", "myshop.co.uk"), ("myshop.co.uk", "myshop.co.uk"), ("a.b.myshop.com.au", "myshop.com.au"),
    ("WWW.Synthetic-Shop.COM.", "synthetic-shop.com"), ("shop.com", "shop.com"), ("203.0.113.5", "203.0.113.5"),
    ("co.uk", "co.uk"), ("x.y.unlisted.com.fj", "com.fj"),
])
def test_Q6_registrable_domain_approximation(host, expected):
    assert registrable_domain(host) == expected


@pytest.mark.parametrize("listing,url", [
    ("https://store.myshop.co.uk/p", "https://myshop.co.uk/authorized"),
    ("https://store.myshop.co.uk/p", "https://blog.myshop.co.uk/authorized"),
    ("https://store.synthetic-shop.com/p", f"https://{SELLER}/authorized"),
    ("https://store.synthetic-shop.com/p", f"https://press.{SELLER}/authorized"),
    ("https://203.0.113.5/p", "https://203.0.113.5/about"),
    ("https://shop.unlisted.com.fj/p", "https://other.unlisted.com.fj/x"),  # over-inclusive fallback withholds only
])
def test_Q6_seller_registrable_domain_evidence_never_lower_risk(listing, url):
    assert decide_for(listing, official(url, listing)).seller_risk != Risk.LOWER_RISK


@pytest.mark.parametrize("listing,url", [
    ("https://store.myshop.co.uk/p", "https://brand.co.uk/retailers"),        # sibling under public suffix
    ("https://store.myshop.co.uk/p", "https://myshop.co.uk.evil-net.com/x"),  # lookalike
    (f"https://{SELLER}/p", f"https://{SELLER}.evil-net.com/retailers"),
    (f"https://{SELLER}/p", f"https://evil{SELLER}/retailers"),
    ("https://203.0.113.5/p", "https://203.0.113.6/retailers"),
    ("https://myshop.com.au/p", "https://brand.com.au/retailers"),
])
def test_Q6_independent_domains_are_not_collapsed_into_the_seller(listing, url):
    assert decide_for(listing, official(url, listing)).seller_risk == Risk.LOWER_RISK


def test_RISK_03_adverse_findings_from_one_registrable_domain_are_not_independent():
    one = evidence(source_url="https://a.regulator-synthetic.gov/action/1", evidence_type="regulatory")
    two = evidence(source_url="https://b.regulator-synthetic.gov/action/2", evidence_type="investigation")
    assert decide_for(LISTING, one, two).seller_risk != Risk.HIGHER_RISK


def test_RISK_03_independent_registrable_domains_still_allow_higher_risk():
    one = evidence(source_url="https://a.regulator-synthetic.gov/action/1", evidence_type="regulatory")
    two = evidence(source_url="https://investigator-synthetic.org/r", evidence_type="investigation")
    assert decide_for(LISTING, one, two).seller_risk == Risk.HIGHER_RISK


# ---------------------------------------------------------------- Q7 mock route

def mock_app(enabled=True, live=True):
    settings = live_settings(enable_mock_sms=enabled) if live else Settings(enable_mock_sms=enabled)
    harness = Harness(settings=settings)
    return harness, harness.app()


EVENT = json.dumps({"event_id": "qa-r3-mock", "text": f"Check {LISTING}"})


@pytest.mark.parametrize("headers,expected", [
    ({"Origin": "https://hostile-page.com", "Content-Type": "application/json"}, 403),
    ({"Origin": "null", "Content-Type": "application/json"}, 403),
    ({"Origin": "chrome-extension://" + "a" * 32, "Content-Type": "application/json"}, 403),
    ({"Content-Type": "text/plain"}, 415),
    ({"Origin": "https://hostile-page.com", "Content-Type": "text/plain"}, 403),
    ({}, 415),
    ({"Content-Type": "application/json-patch+json"}, 415),
], ids=["hostile_origin", "null_origin", "extension_origin", "text_plain", "origin_and_text", "no_type", "json_patch"])
def test_Q7_mock_route_rejects_browser_requests_before_any_work(headers, expected):
    harness, app = mock_app()
    with TestClient(app) as client:
        response = client.post("/api/v1/mock/messages", content=EVENT, headers=headers)
        client.get("/healthz")
    assert response.status_code == expected
    assert harness.calls == [] and len(app.state.transport.sent) == 0


def test_Q7_mock_route_disabled_is_404_even_for_valid_json():
    harness, app = mock_app(enabled=False)
    with TestClient(app) as client:
        for headers in [{"Content-Type": "application/json"}, {"Origin": "https://hostile-page.com"}]:
            assert client.post("/api/v1/mock/messages", content=EVENT, headers=headers).status_code == 404
    assert harness.calls == []


def test_Q7_mock_route_declared_and_chunked_oversize_rejected():
    harness, app = mock_app()

    def chunks():
        for _ in range(10):
            yield b"a" * 4096
    with TestClient(app) as client:
        assert client.post("/api/v1/mock/messages", content=b"x" * 20000, headers={"Content-Type": "text/plain"}).status_code == 413
        assert client.post("/api/v1/mock/messages", content=chunks(), headers={"Content-Type": "application/json"}).status_code == 413
    assert harness.calls == []


def test_Q7_mock_route_still_works_for_local_json_and_stays_labeled():
    harness, app = mock_app(live=False)
    with TestClient(app) as client:
        response = client.post("/api/v1/mock/messages", content=EVENT, headers={"Content-Type": "application/json"})
        client.get("/healthz")
    assert response.status_code == 202 and response.json()["data_mode"] == "mock"
    assert app.state.transport.sent[0][1].startswith("MOCK SIMULATION: ")


# ---------------------------------------------------------------- QA-06 origin wording

def origin_status(quote):
    sheet = PromiseSheet.model_validate({"seller_domain": SELLER, "sources": [source("a", LISTING, quote)],
                                         "records": [row("shipping_origin", "supported_as_statement", [("a", quote)])]})
    return [r.status for r in validate_promise_sheet(sheet, sheet.sources).records]


@pytest.mark.parametrize("quote", [
    "SHIPS\nFROM our Ohio depot.", "Ships from Lyon.", "Country of origin: France.", "Origin: Grasse, France.",
    "All parcels are dispatched   from Milan.", "Orders leave our warehouse in Newark.", "Shipped from Paris.",
])
def test_QA06_whole_word_origin_wording_is_recognized(quote):
    assert origin_status(quote) == ["supported_as_statement"]


@pytest.mark.parametrize("quote", [
    "Original packaging. 100 Pike Street, Seattle.", "Originally founded in Seattle at 100 Pike Street.",
    "Aboriginal art prints, 100 Pike Street.", "With your consent from checkout we bill 100 Pike Street.",
    "Our warehouses-style showroom at 100 Pike Street.", "Shipsfrom 100 Pike Street", "Our origins: 100 Pike Street, Seattle.",
])
def test_QA06_substrings_and_lookalike_words_do_not_count(quote):
    assert origin_status(quote) == ["not_disclosed"]


# ---------------------------------------------------------------- QA-08 link neutralizing

@pytest.mark.parametrize("text", [
    "phish-аttacker.com", "evil。com", "evil．com/claim", "evil｡com", "ｅｖｉｌ．ｃｏｍ",
    "xn--80ak6aa92e.com", "evil.xn--p1ai", "203.0.113.9:8080/claim", "203.0.113.9", "198.51.100.7/x?y=1",
    "user@evil.io", "tel:+15550109999", "sms:+15550109999", "facetime:x@evil.com", "data:text/html,<b>x</b>",
    "EVIL.COM/Path", "sub.evil.shop", "evil.co.uk", "days.Free/phish.com", "пример.рф",
])
def test_QA08_linkish_tokens_in_merchant_text_are_neutralized(text):
    out = neutralize_links(f"Free returns. Visit {text} now.")
    assert LINK_REMOVED in out
    assert not URL_RE.search(out)
    for fragment in ["evil", "phish", "attacker", "203.0.113", "198.51", "5550109999", "при"]:
        assert fragment not in out.replace("days.Free/", ""), out


@pytest.mark.parametrize("text", ["2-3 days.Free returns", "Dr.Smith", "Chanel No.5", "Version 2.5 formula", "50ml.Thanks"])
def test_QA08_ordinary_prose_without_real_tld_survives(text):
    assert neutralize_links(text) == text


@pytest.mark.parametrize("payload", ["a" * 1200, ("a." * 600), ("a-" * 600), ("1." * 600), ("а." * 600)])
def test_QA08_neutralizer_has_no_pathological_backtracking(payload):
    start = time.perf_counter()
    neutralize_links(payload)
    assert time.perf_counter() - start < 0.5


def test_QA08_full_phone_reply_has_only_labeled_links_for_mixed_attack_quote():
    content = ("Free returns. Help: phish-аttacker.com, evil。com, 203.0.113.9:8080/x, tel:+15550109999, "
               "WWW.EVIL.SHOP and xn--80ak6aa92e.com.")
    sheet = PromiseSheet.model_validate({"seller_domain": SELLER, "sources": [source("a", f"https://{SELLER}/returns", content)],
                                         "records": [row("returns", "supported_as_statement", [("a", content)])]})
    text = format_sms(base_assessment(promise_sheet=validate_promise_sheet(sheet, sheet.sources)))
    assert set(URL_RE.findall(text)) == {f"https://{SELLER}/returns"}
    assert text.count(LINK_REMOVED) == 6


# ---------------------------------------------------------------- QA-07 brackets and possessives

@pytest.mark.parametrize("message,expected", [
    ("Check this listing <https://synthetic-shop.com/p?>", "https://synthetic-shop.com/p?"),
    ("Check this listing <https://synthetic-shop.com/p).> price $5", "https://synthetic-shop.com/p)."),
    ("See <https://synthetic-shop.com/p>.", "https://synthetic-shop.com/p"),
    ("Is https://synthetic-shop.com's listing legit?", "https://synthetic-shop.com/"),
    ("Is https://synthetic-shop.com:443's listing legit?", "https://synthetic-shop.com/"),
    ("Check https://synthetic-shop.com/it's-50ml", "https://synthetic-shop.com/it's-50ml"),
    ("Check 'https://synthetic-shop.com/p'", "https://synthetic-shop.com/p"),
    ("<https://synthetic-shop.com/p's>", "https://synthetic-shop.com/p's"),
])
def test_QA07_bracket_and_apostrophe_boundaries(message, expected):
    assert _provided_urls(message) == {expected}


@pytest.mark.parametrize("message,expected", [
    ("Check https://x-shop.com/p.", "https://x-shop.com/p"),
    ("Check https://x-shop.com/p. Is it legit?", "https://x-shop.com/p"),
    ("Check https://x-shop.com/p, thanks", "https://x-shop.com/p"),
    ("(see https://x-shop.com/p)", "https://x-shop.com/p"),
    ("Is https://en.x-shop.com/wiki/Perfume_(100ml) legit?", "https://en.x-shop.com/wiki/Perfume_(100ml)"),
    ("Check https://x-shop.com/it's-50ml!", "https://x-shop.com/it's-50ml"),
])
def test_QA07_phone_prose_rule_unchanged(message, expected):
    assert _provided_urls(message) == {expected}


def test_QA07_bracket_inside_url_cannot_split_or_smuggle_a_second_url():
    assert _provided_urls("Check <https://synthetic-shop.com/a>https://evil-shop.com/b>") == {
        "https://synthetic-shop.com/a", "https://evil-shop.com/b"}  # two URLs -> clarification, never a silent pick
    assert len(_provided_urls("Check <https://synthetic-shop.com/a<https://evil-shop.com/b>")) == 2


def test_QA07_very_long_extension_url_round_trips_and_is_researched_verbatim():
    href = f"https://{SELLER}/p?" + "&".join(f"k{i}=v{i}" for i in range(220))
    href = href[:2040] + "x."
    assert len(href) <= 2048
    message = f"Check this listing <{href}> price $89.99"
    assert len(message) <= 4000
    assert _provided_urls(message) == {href}
    harness = Harness(plan=plan_output(product_url=href))
    response = harness.post(text=message)
    assert response.status_code == 200
    assert harness.dns and harness.dns[0] == href
    assert harness.calls[:2] == ["shopping_plan", "/search"]


def test_QA07_trailing_dot_listing_from_extension_reaches_research_end_to_end():
    href = f"https://{SELLER}/perfume."
    harness = Harness(plan=plan_output(product_url=href))
    body = harness.post(path="/api/v1/extension/evaluate", text=f"Check this listing <{href}>",
                        headers={"Authorization": "Bearer qa-synthetic-pairing-token"}).json()
    assert body["assessment"]["decision"] == "VERIFY_FIRST"
    assert harness.dns[0] == href
