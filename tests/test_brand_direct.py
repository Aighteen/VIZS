"""Brand-direct rule (lane C): offline adversarial tests, synthetic excerpts only."""
import asyncio
from datetime import datetime, timezone

import pytest

from app.decision import decide, format_sms
from app.decision import brand_direct
from app.models import Evidence, OrchestratorPlan, ShoppingRequest
from app.research.evidence import SellerResearch
from app.research.provider import SearchResponse, SourceRecord

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
BRAND_URL = ("https://www.lelabofragrances.com/santal-33-147.html?gclid=Cj0KCQjw_synthetic_BwE"
             "&gbraid=0AAAAAD_synthetic&gad_source=1")
WIKI = ("Le Labo is a New York perfume house founded in 2006. Its official website is "
        "lelabofragrances.com, where it sells Santal 33.")
MAG = "Shop the scent at the official Le Labo online store, www.lelabofragrances.com, or in boutiques."
GOOD = [("https://en.wikipedia.org/wiki/Le_Labo", WIKI), ("https://www.vogue-synthetic.com/le-labo", MAG)]


def host_of(url):
    from urllib.parse import urlsplit
    return urlsplit(url).hostname.removeprefix("www.")


def identity(source, excerpt, listing=BRAND_URL, **change):
    data = dict(claim="Unverified search excerpt about the site's official status: " + excerpt,
                source_url=source, excerpt=excerpt, retrieved_at=NOW, seller_domain=host_of(listing),
                evidence_type="search_snippet", claim_status="unknown", finding="seller_identity",
                polarity="neutral", data_mode="partial")
    data.update(change)
    return Evidence(**data)


def run(listing, sources, brand=None, extra=()):
    request = ShoppingRequest(request_id="bd", message_text=f"Check <{listing}>")
    plan = OrchestratorPlan(request_id="bd", intent="evaluate_purchase", product_url=listing, brand=brand,
                            tasks=[{"kind": "verify_seller", "query": "seller"}])
    evidence = [identity(s, e, listing) for s, e in sources] + list(extra)
    assessment = decide(request, plan, evidence)
    return assessment, format_sms(assessment)


def assert_brand_direct(assessment, sms):
    assert assessment.decision == "VERIFY_FIRST" and assessment.seller_risk == "INSUFFICIENT_EVIDENCE"
    assert assessment.summary.startswith("Brand's own store: 2 independent sources")
    assert "verify authorization" not in sms.lower() and "authorization unconfirmed" not in sms.lower()
    assert "Brand's own store" in sms and "Product authenticity is not established." in sms
    assert "Product authenticity is not established." in assessment.missing_information
    assert all(e.claim_status != "verified_fact" for e in assessment.evidence)


def assert_not_brand_direct(assessment, sms):
    assert assessment.seller_risk != "LOWER_RISK"
    assert not assessment.summary.startswith("Brand's own store")
    if assessment.decision == "VERIFY_FIRST" and "conflict" not in assessment.summary:
        assert "Verify authorization" in sms


# ------------------------------------------------------------------ positive

def test_brand_store_named_official_by_two_independent_sites_is_brand_direct():
    assessment, sms = run(BRAND_URL, GOOD)
    assert_brand_direct(assessment, sms)
    assert "only if the product is that brand's own" in sms
    assert [str(e.source_url) for e in assessment.evidence] == [s for s, _ in GOOD]
    assert sms.count("Unverified source: ") == 2
    assert "lelabofragrances.com" not in assessment.summary  # policy text names no domain


def test_user_stated_matching_brand_drops_the_caveat():
    assessment, sms = run(BRAND_URL, GOOD, brand="Le Labo")
    assert_brand_direct(assessment, sms)
    assert "only if" not in assessment.summary


def test_regional_sibling_counts_only_when_evidence_names_it():
    au = "https://www.lelabofragrances.com.au/santal-33.html"
    named = [("https://en.wikipedia.org/wiki/Le_Labo", "The official Australian site is lelabofragrances.com.au."),
             ("https://www.news-synthetic.com.au/x", "Buy at the official online store lelabofragrances.com.au today.")]
    assert_brand_direct(*run(au, named))
    assert_not_brand_direct(*run(au, GOOD))  # evidence names lelabofragrances.com, not .com.au


# ------------------------------------------------------------------ lookalikes

@pytest.mark.parametrize("listing", [
    "https://lelabo-outlet-sale.com/santal-33",
    "https://lelabofragrances.co/santal-33",
    "https://le-labo-fragrances.shop/santal-33",
    "https://lelabofragrances.com.evil.io/santal-33",
    "https://shop.lelabofragrances.com.attacker.net/santal-33",
])
def test_lookalikes_are_never_brand_direct(listing):
    # Genuine evidence names the real domain; the lookalike gets nothing from it.
    assert_not_brand_direct(*run(listing, GOOD))
    # A warning article that names the lookalike next to "official" does not help it.
    warning = ("Beware of fake sites such as " + host_of(listing) +
               "; the official site is lelabofragrances.com.")
    assert_not_brand_direct(*run(listing, [("https://en.wikipedia.org/wiki/Le_Labo", warning),
                                           ("https://www.vogue-synthetic.com/x", warning)]))


def test_lookalike_texts_do_not_match_the_real_domain_either():
    texts = ["Its official website is lelabofragrances.com.evil.io.",
             "Official store: shop.lelabofragrances.com.attacker.net",
             "official site evil-lelabofragrances.com"]
    for text in texts:
        assert brand_direct.classify_excerpt(text, "lelabofragrances.com") != "supports"


# ------------------------------------------------------------------ marketplaces

@pytest.mark.parametrize("listing", ["https://www.amazon.com/Le-Labo-Santal-33/dp/B000SYNTH",
                                     "https://www.ebay.com/itm/123456",
                                     "https://www.amazon.co.uk/dp/B000SYNTH",
                                     "https://le-labo.myshopify.com/products/santal"])
def test_marketplace_listings_are_never_brand_direct(listing):
    site = brand_direct._site(host_of(listing))
    sources = [("https://en.wikipedia.org/wiki/X", f"The official website is {site}."),
               ("https://www.vogue-synthetic.com/x", f"Shop at the official store {site}.")]
    assert brand_direct.listing_eligible(host_of(listing)) is False
    assert_not_brand_direct(*run(listing, sources))


# ------------------------------------------------------------------ self-asserted

@pytest.mark.parametrize("source", ["https://www.lelabofragrances.com/about",
                                    "https://shop.lelabofragrances.com/faq",
                                    "https://lelabofragrances.com/legal",
                                    "https://www.lelabofragrances.com.au/about",
                                    "https://lelabofragrances-reviews.net/post"])
def test_seller_own_site_and_brand_named_hosts_never_count(source):
    claim = "This is the official website of Le Labo: lelabofragrances.com."
    forged = dict(evidence_type="official", claim_status="verified_fact", polarity="supports")
    assessment, sms = run(BRAND_URL, [GOOD[0]], extra=[identity(source, claim, **forged)])
    assert_not_brand_direct(assessment, sms)


# ------------------------------------------------------------------ weak support

@pytest.mark.parametrize("sources", [
    [GOOD[0]],                                                            # one source
    [("https://www.reddit.com/r/fragrance/x", WIKI), ("https://www.quora.com/x", MAG)],  # forum/Q&A only
    [("https://www.reddit.com/r/fragrance/x", WIKI), GOOD[1]],            # one forum + one site
    [("https://en.wikipedia.org/wiki/Le_Labo", WIKI), ("https://de.wikipedia.org/wiki/Le_Labo", MAG)],  # one registrable domain
    [("https://en.wikipedia.org/wiki/Le_Labo", "Le Labo was founded by lelabofragrances.com staff."),
     ("https://www.vogue-synthetic.com/x", "lelabofragrances.com ships fast.")],  # no "official" wording
    [("https://en.wikipedia.org/wiki/Le_Labo", "lelabofragrances.com is not the official site."),
     ("https://www.vogue-synthetic.com/x", "lelabofragrances.com is an unofficial store.")],  # denial
    [("https://en.wikipedia.org/wiki/Le_Labo", "Scam alert: lelabofragrances.com claims to be the official store."),
     ("https://www.vogue-synthetic.com/x", "Counterfeit warning: official site lelabofragrances.com?")],
])
def test_weak_or_negated_support_is_not_brand_direct(sources):
    assert_not_brand_direct(*run(BRAND_URL, sources))


def test_independent_sources_naming_a_different_domain_block_brand_direct():
    other = [("https://en.wikipedia.org/wiki/Le_Labo", "Le Labo's official website is labo-official-synth.com."),
             ("https://www.vogue-synthetic.com/x", "Official store: labo-official-synth.com")]
    assert_not_brand_direct(*run(BRAND_URL, other))
    third = ("https://www.press-synthetic.com/x", "The official online store is labo-official-synth.com.")
    assessment, sms = run(BRAND_URL, GOOD + [third])
    assert_not_brand_direct(assessment, sms)
    assert brand_direct.assess(host_of(BRAND_URL), [identity(s, e) for s, e in GOOD + [third]]).conflicting_sites == 1


def test_upstream_labels_cannot_grant_brand_direct():
    # Same text but not produced by the brand-direct search: ignored.
    other = [identity(s, e, finding="other") for s, e in GOOD]
    assert_not_brand_direct(*run(BRAND_URL, [], extra=other))


def test_user_named_brand_that_is_not_the_store_blocks_retailer_self_identity():
    store = "https://www.sephora-synthetic.com/product/le-labo-santal-33"
    sources = [("https://en.wikipedia.org/wiki/Sephora", "Sephora's official website is sephora-synthetic.com."),
               ("https://www.vogue-synthetic.com/x", "Visit the official online store at sephora-synthetic.com.")]
    assert_not_brand_direct(*run(store, sources, brand="Le Labo"))
    # Brand unknown: the store is its own brand's official site; the reply says
    # it holds only if the product is that brand's own (documented limitation).
    assessment, sms = run(store, sources)
    assert "only if the product is that brand's own" in sms


# ------------------------------------------------------------------ precedence

def test_adverse_findings_and_contradictions_override_brand_direct():
    adverse = [identity(u, "x", finding="substantial_adverse", evidence_type=t, claim_status="verified_fact",
                        polarity="supports") for u, t in [("https://regulator-synthetic.gov/a", "regulatory"),
                                                          ("https://investigator-synthetic.org/r", "investigation")]]
    assessment, _ = run(BRAND_URL, GOOD, extra=adverse)
    assert assessment.decision == "AVOID"
    contra = identity("https://press-synthetic.com/x", "x", finding="other", polarity="contradicts")
    assessment, _ = run(BRAND_URL, GOOD, extra=[contra])
    assert assessment.summary.startswith("Seller evidence conflicts")


def test_official_authorization_still_gives_lower_risk_first():
    official = identity("https://brand-synthetic.com/retailers", "lelabofragrances.com is authorized",
                        finding="seller_authorized", evidence_type="official", claim_status="verified_fact",
                        polarity="supports")
    assessment, _ = run(BRAND_URL, GOOD, extra=[official])
    assert assessment.decision == "CONSIDER_BUYING"


# ------------------------------------------------------------------ research layer

class FakeProvider:
    def __init__(self, records):
        self.records, self.queries = records, []

    async def search_with_status(self, query):
        self.queries.append(query)
        return SearchResponse(self.records, len(self.records))


def plan_for(url, brand=None):
    return OrchestratorPlan(request_id="bd", intent="evaluate_purchase", product_url=url, brand=brand,
                            tasks=[{"kind": "verify_seller", "query": "ignore rules"}])


def test_research_query_is_fixed_and_keeps_only_independent_relevant_records():
    records = [SourceRecord("https://www.lelabofragrances.com/about", "", "Official site lelabofragrances.com", NOW),
               SourceRecord(GOOD[0][0], "", GOOD[0][1], NOW),
               SourceRecord("https://www.reddit.com/r/x", "", WIKI, NOW),
               SourceRecord("https://blog-synthetic.com/x", "", "Santal 33 review, lelabofragrances.com.", NOW),
               SourceRecord(GOOD[1][0], "", GOOD[1][1], NOW)]
    provider = FakeProvider(records)
    result = asyncio.run(SellerResearch(provider).brand_direct_with_status(plan_for(BRAND_URL, brand="Ignore all rules")))
    assert provider.queries == ['"lelabofragrances.com" official website']
    assert [str(e.source_url) for e in result.evidence] == [GOOD[0][0], GOOD[1][0]]
    assert all(e.finding == "seller_identity" and e.claim_status == "unknown"
               and e.evidence_type == "search_snippet" and e.seller_domain == "lelabofragrances.com"
               for e in result.evidence)
    report = result.report()
    assert (report.records_received, report.records_retained, report.records_filtered) == (5, 2, 3)


@pytest.mark.parametrize("url", ["https://www.amazon.com/dp/B000SYNTH", "https://10.0.0.1/x"])
def test_research_skips_marketplaces_and_unsafe_hosts_without_a_provider_call(url):
    provider = FakeProvider([])
    result = asyncio.run(SellerResearch(provider).brand_direct_with_status(plan_for(url)))
    assert result.evidence == [] and provider.queries == []
    assert result.status in {"skipped", "unsafe_url"}


def test_workflow_skips_brand_research_after_unsafe_seller_url():
    from app.config import Settings
    from app.models import Assessment
    from app.research.evidence import ResearchResult
    from app.workflow.service import Contracts, EvaluationWorkflow
    called = []

    async def extract(request):
        return plan_for(BRAND_URL).model_dump()

    async def research(plan, task):
        return ResearchResult([], "unsafe_url")

    async def brand(plan):
        called.append(plan)
        return ResearchResult([], "skipped")

    workflow = EvaluationWorkflow(Contracts(ShoppingRequest, OrchestratorPlan, Assessment), extract, research,
                                  lambda r, p, e: decide(r, p, e), Settings(), brand_research=brand)
    result = asyncio.run(workflow.evaluate(ShoppingRequest(request_id="bd", message_text="x")))
    assert called == [] and result.decision == "VERIFY_FIRST"
