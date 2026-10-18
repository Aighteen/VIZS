"""Brand-direct rule (lane C): offline adversarial tests, synthetic excerpts only."""
import asyncio
import re
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


# Reference-source excerpts are page spans that include the article lead
# (see test_reference_page_*). Synthetic reference excerpts get a brand lead by
# default so each negative below fails for its own reason, not a missing lead.
BRAND_LEAD = "**Le Labo** is a perfumery brand founded in New York in 2006.\n"


def identity(source, excerpt, listing=BRAND_URL, lead=BRAND_LEAD, **change):
    if lead and brand_direct.is_reference(host_of(source)):
        excerpt = lead + excerpt
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
    # Human decision 2026-10-17: brand-direct is LOWER_RISK / CONSIDER_BUYING.
    assert assessment.decision == "CONSIDER_BUYING" and assessment.seller_risk == "LOWER_RISK"
    assert assessment.summary.startswith("Brand's own store: per 1 reference source")
    assert "INSUFFICIENT_EVIDENCE" not in sms and sms.startswith("[PARTIAL DATA] LOWER_RISK: Brand's own store")
    assert "Check return terms before buying." in sms
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
    assert f"Brand-store reference (unverified): {GOOD[0][0]}" in sms
    assert sms.count("Unverified source: ") == 1 and GOOD[1][0] in sms
    assert "lelabofragrances.com" not in assessment.summary  # policy text names no domain


def test_one_curated_reference_source_is_enough_and_counts_once_per_domain():
    assessment, sms = run(BRAND_URL, [GOOD[0]])
    assert assessment.summary.startswith("Brand's own store: per 1 reference source, this site")
    assert "verify authorization" not in sms.lower()
    both = [("https://en.wikipedia.org/wiki/Le_Labo", WIKI), ("https://de.wikipedia.org/wiki/Le_Labo", MAG)]
    assert run(BRAND_URL, both)[0].summary.startswith("Brand's own store: per 1 reference source, this site")


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
    assessment, sms = run(BRAND_URL, [GOOD[1]], extra=[identity(source, claim, **forged)])
    assert_not_brand_direct(assessment, sms)


# ------------------------------------------------------------------ weak support

@pytest.mark.parametrize("sources", [
    [GOOD[1]],                                                            # one non-reference source
    [GOOD[1], ("https://www.press-synthetic.com/x", MAG)],                # unvetted pages only (C7)
    [("https://www.reddit.com/r/fragrance/x", WIKI), ("https://www.quora.com/x", MAG)],  # forum/Q&A only
    [("https://www.reddit.com/r/fragrance/x", WIKI), GOOD[1]],            # one forum + one site
    [("https://a.press-synthetic.com/x", WIKI), ("https://b.press-synthetic.com/y", MAG)],  # one registrable domain
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


@pytest.mark.parametrize("lead", [
    # Live false positive 2026-10-17 (shape): a multi-brand beauty retailer whose
    # Wikipedia infobox names its own domain.
    "**Bluemercury** is an American luxury beauty products and spa retailer.\n",
    "**Sephora** is a multinational retailer of personal care and beauty products.\n",
    "**Nordstrom, Inc.** is an American luxury department store chain.\n",
    "**Shop Synthetic** is an e-commerce platform for independent brands.\n",
    "**Perfume Synthetic** is an authorized distributor of designer fragrance brands.\n",
    "**Synthetic Store** is a company.\n",          # no brand/maker wording at all
    "Synthetic Store is a perfumery brand.\n",       # not a lead line (no bold subject)
])
def test_reference_source_lead_must_describe_a_brand_not_a_retailer(lead):
    store = "https://www.retail-synthetic.com/products/le-labo-santal-33"
    reference = identity("https://en.wikipedia.org/wiki/Retail", "| Website | <https://www.retail-synthetic.com> |",
                         store, lead=lead)
    other = identity("https://www.vogue-synthetic.com/x", "Shop at the official store retail-synthetic.com.", store)
    assert_not_brand_direct(*run(store, [], extra=[reference, other]))
    assert brand_direct.lead_describes_brand(lead + "| Website | x |") is False


def test_brand_lead_with_infobox_row_is_brand_direct():
    reference = identity("https://en.wikipedia.org/wiki/Allbirds", "| Website | [allbirds.com](http://allbirds.com) |",
                         "https://www.allbirds.com/products/x",
                         lead="**Allbirds** is an American [footwear](https://en.wikipedia.org/wiki/Footwear) "
                              "and apparel brand that was co-founded in 2015.\n")
    assessment, sms = run("https://www.allbirds.com/products/x", [], extra=[reference])
    assert assessment.seller_risk == "LOWER_RISK" and sms.startswith("[PARTIAL DATA] LOWER_RISK: Brand's own store")


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
    assert assessment.summary.startswith("Official seller authorization") and assessment.evidence == [official]


@pytest.mark.parametrize("kind", ["regulatory", "investigation"])
def test_a_single_adverse_finding_blocks_brand_direct_lower_risk(kind):
    adverse = identity("https://regulator-synthetic.gov/a", "x", finding="substantial_adverse", evidence_type=kind,
                       claim_status="verified_fact", polarity="supports")
    assessment, sms = run(BRAND_URL, GOOD, extra=[adverse])
    assert assessment.seller_risk != "LOWER_RISK" and assessment.decision == "VERIFY_FIRST"
    assert not assessment.summary.startswith("Brand's own store")


# ------------------------------------------------------------------ research layer

class FakeProvider:
    def __init__(self, records):
        self.records, self.queries = records, []

    async def search_with_status(self, query, include_domains=()):
        self.queries.append(query)
        self.filters = getattr(self, "filters", []) + [include_domains]
        records = self.wiki_records if include_domains else self.records
        return SearchResponse(records, len(records))

    wiki_records = []


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


# ------------------------------------------------------------------ threat model C1-C15
# docs/reviews/BRAND_DIRECT_THREAT_MODEL.md (lane E). Cases not listed here are
# covered above: C6 (self-asserted), C10 (regional siblings), C14 (precedence).

BANNED_WORDS = ("authentic ", "genuine", "guarantee", "safe to buy", "counterfeit")


@pytest.mark.parametrize("host", [
    "lelabo-outlet-sale.com", "le-labo-fragrances.shop", "lelabofragrances.co", "lelabofragrance.com",
    "lelabofragrances-official.com", "lelabofragrances.com.evil.io", "www.lelabofragrances.com.evil.io",
    "lelabofragrances.com-shop.io", "xn--llabofragrances-4nm.com", "lеlabofragrances.com",
    "brand-sale.myshopify.com", "shop.lelabofragrances.com.attacker.net",
])
def test_C1_C2_C3_lookalike_suffix_append_and_homoglyph_hosts(host):
    listing = f"https://{host}/santal-33"
    assert_not_brand_direct(*run(listing, GOOD))
    # Sources that also name the listing next to the real domain do not help it.
    mixed = [(s, e + f" Also seen: {host}.") for s, e in GOOD]
    assert_not_brand_direct(*run(listing, mixed))


def test_C2_registrable_domain_of_suffix_append_is_the_attacker():
    from app.decision.rules import registrable_domain
    assert registrable_domain("lelabofragrances.com.evil.io") == "evil.io"
    assert brand_direct.grant_key("www.lelabofragrances.com.evil.io") == ("evil.io", True)


@pytest.mark.parametrize("listing", ["https://LELABOFRAGRANCES.COM./santal-33",
                                     "https://www.lelabofragrances.com/santal-33",
                                     "https://lelabofragrances.com/santal-33"])
def test_C3_real_domain_spelling_variants_still_match(listing):
    assert_brand_direct(*run(listing, GOOD))


def test_C4_shared_platform_and_unlisted_suffix_need_the_exact_host():
    shop = [("https://en.wikipedia.org/wiki/Brand", "The official store is brand.myshopify.com."),
            ("https://www.vogue-synthetic.com/x", "Shop at the official store brand.myshopify.com.")]
    assert_not_brand_direct(*run("https://brand-sale.myshopify.com/products/x", shop))
    assert_not_brand_direct(*run("https://brand.myshopify.com/products/x", shop))  # platforms: never
    ph = [("https://en.wikipedia.org/wiki/Brand", "The official website is brand.net.ph."),
          ("https://www.vogue-synthetic.com/x", "Buy at the official online store brand.net.ph.")]
    assert brand_direct.grant_key("evil.net.ph") == ("evil.net.ph", False)
    assert_not_brand_direct(*run("https://evil.net.ph/p", ph))
    assert_not_brand_direct(*run("https://shop.brand.net.ph/p", ph))  # exact host only
    assert_brand_direct(*run("https://brand.net.ph/p", ph))
    for host in ["brand.github.io", "brand.netlify.app", "brand.vercel.app", "brand.pages.dev",
                 "brand.web.app", "brand.wixsite.com", "brand.square.site", "brand.blogspot.com"]:
        assert brand_direct.listing_eligible(host) is False, host


@pytest.mark.parametrize("listing", ["https://www.amazon.com/stores/LeLabo/page/SYNTHETIC",
                                     "https://www.sephora.com/product/le-labo-santal-33",
                                     "https://www.nordstrom.com/s/le-labo-santal-33/5000033",
                                     "https://www.ulta.com/p/santal", "https://www.farfetch.com/shopping/x",
                                     "https://shop.app/products/123"])
def test_C5_marketplaces_and_multibrand_retailers(listing):
    site = brand_direct._site(host_of(listing))
    sources = [("https://en.wikipedia.org/wiki/X", f"Le Labo runs an official storefront on {site}."),
               ("https://www.vogue-synthetic.com/x", f"Le Labo is available at {site}, its official store there.")]
    assessment, sms = run(listing, sources)
    assert_not_brand_direct(assessment, sms)
    assert "official store" not in assessment.summary.lower()


def test_C7_agreeing_unvetted_pages_are_not_enough():
    spam = [(f"https://www.{d}/le-labo", "The official Le Labo site is lelabo-outlet-sale.com.")
            for d in ("best-perfume-deals.net", "scent-reviews-synthetic.org", "top10-fragrance-synthetic.com")]
    forged = [identity(s, e, "https://lelabo-outlet-sale.com/x", evidence_type="official") for s, e in spam]
    assert_not_brand_direct(*run("https://lelabo-outlet-sale.com/x", [], extra=forged))
    # The same three pages naming the real domain are still not enough without a reference source.
    real = [(s, "The official Le Labo site is lelabofragrances.com.") for s, _ in spam]
    assert_not_brand_direct(*run(BRAND_URL, real))
    # The real brand linking to the lookalike as a partner does not make it official.
    partner = [("https://www.lelabofragrances.com/partners", "Our partner lelabo-outlet-sale.com."),
               ("https://en.wikipedia.org/wiki/Le_Labo", WIKI)]
    assert_not_brand_direct(*run("https://lelabo-outlet-sale.com/x", partner))


def test_C8_user_text_and_plan_brand_never_create_the_mapping():
    listing = "https://lelabo-outlet-sale.com/santal"
    request = ShoppingRequest(request_id="bd", message_text=f"Le Labo official store {listing}")
    plan = OrchestratorPlan(request_id="bd", intent="evaluate_purchase", product_url=listing, brand="Le Labo")
    assessment = decide(request, plan, [])
    assert_not_brand_direct(assessment, format_sms(assessment))
    # The search query is built from the listing domain only, never from model text.
    provider = FakeProvider([])
    asyncio.run(SellerResearch(provider).brand_direct_with_status(
        plan_for(listing, brand="lelabofragrances.com official")))
    assert set(provider.queries) == {'"lelabo-outlet-sale.com" official website'}  # incl. Wikipedia fallback


def test_C9_other_brand_on_the_real_domain_gets_no_brand_direct_wording():
    assert_not_brand_direct(*run(BRAND_URL, GOOD, brand="Byredo"))


def test_C11_provider_records_cannot_change_the_listing_host():
    # Records relabeled as being about the real domain do not apply to a lookalike listing.
    relabeled = [identity(s, e, BRAND_URL) for s, e in GOOD]
    assert_not_brand_direct(*run("https://lelabo-outlet-sale.com/x", [], extra=relabeled))


@pytest.mark.parametrize("brand", [None, "Le Labo"])
def test_C12_brand_direct_wording_never_overclaims(brand):
    assessment, sms = run(BRAND_URL, GOOD, brand=brand)
    for text in (assessment.summary.lower(), sms.lower().replace("product authenticity is not established.", "")):
        assert not any(word in text for word in BANNED_WORDS), text
        assert "authentic" not in text


def test_C13_unknown_seller_with_low_price_is_not_fraud():
    request = ShoppingRequest(request_id="bd", message_text="https://small-candle-synthetic.com/p $1")
    plan = OrchestratorPlan(request_id="bd", intent="evaluate_purchase",
                            product_url="https://small-candle-synthetic.com/p", purchase_price="1")
    assessment = decide(request, plan, [])
    assert assessment.seller_risk == "INSUFFICIENT_EVIDENCE" and assessment.decision == "VERIFY_FIRST"


def test_C15_reference_registry_is_immutable_and_plain_ascii():
    assert isinstance(brand_direct.REFERENCE_SOURCES, frozenset)
    for site in brand_direct.REFERENCE_SOURCES:
        assert site == site.lower() and site.isascii() and not site.startswith("xn--") and "." in site


# ------------------------------------------------------------------ reference page (live calibration)
# Live 2026-10-17: Tavily search snippets for '"lelabofragrances.com" official website'
# did not name the domain; the Wikipedia page extracted as markdown has the infobox row
# "| Website | <https://www.lelabofragrances.com> |" (shape reproduced synthetically).

WIKI_PAGE = ("# Le Labo\n\n| Type | Subsidiary |\n| Industry | Consumer goods |\n"
             "| Parent | Estée Lauder Companies |\n| Website | <https://www.lelabofragrances.com> |\n\n"
             "**Le Labo** (French: the lab) is a slow perfumery brand born in Grasse, France.\n\n## History\n")
RETAILER_PAGE = WIKI_PAGE.replace("is a slow perfumery brand born in Grasse, France",
                                  "is an American luxury beauty products and spa retailer")


class ExtractingProvider(FakeProvider):
    def __init__(self, records, pages):
        super().__init__(records)
        self.pages, self.extracted = pages, []

    async def extract_sources(self, urls, *, markdown=False, max_chars=12000, content_kind="merchant_page"):
        self.extracted.append((urls, markdown, content_kind))
        return [SourceRecord(u, "Retrieved reference page", self.pages[u][:max_chars], NOW, content_kind=content_kind)
                for u in urls if u in self.pages]


WIKI_URL = "https://en.wikipedia.org/wiki/Le_Labo"
NEUTRAL_WIKI = SourceRecord(WIKI_URL, "Le Labo - Wikipedia", "Le Labo is a slow perfumery brand born in Grasse.", NOW)


def brand_research(listing, records, pages):
    provider = ExtractingProvider(records, pages)
    return provider, asyncio.run(SellerResearch(provider).brand_direct_with_status(plan_for(listing)))


def test_reference_page_infobox_row_confirms_the_exact_domain():
    provider, result = brand_research(BRAND_URL, [NEUTRAL_WIKI], {WIKI_URL: WIKI_PAGE})
    assert provider.extracted == [([WIKI_URL], True, "reference_page")]
    assert [e.excerpt for e in result.evidence] == [
        "| Website | <https://www.lelabofragrances.com> |\n\n"
        "**Le Labo** (French: the lab) is a slow perfumery brand born in Grasse, France."]
    assert result.evidence[0].excerpt in WIKI_PAGE  # exact span of retrieved text
    report = result.report()
    assert report.records_retained == 1 and report.records_received == 1
    assessment, sms = run(BRAND_URL, [], extra=result.evidence)
    assert assessment.summary.startswith("Brand's own store: per 1 reference source, this site")
    assert assessment.seller_risk == "LOWER_RISK" and assessment.decision == "CONSIDER_BUYING"
    assert "verify authorization" not in sms.lower() and f"Brand-store reference (unverified): {WIKI_URL}" in sms


@pytest.mark.parametrize("listing", ["https://lelabo-outlet-sale.com/x", "https://lelabofragrances.co/x",
                                     "https://www.lelabofragrances.com.au/x", "https://lelabofragrances.com.evil.io/x"])
def test_reference_page_naming_the_real_domain_does_not_help_lookalikes(listing):
    _, result = brand_research(listing, [NEUTRAL_WIKI], {WIKI_URL: WIKI_PAGE})
    assert result.evidence == []
    assert_not_brand_direct(*run(listing, [], extra=result.evidence))


def test_reference_page_of_a_retailer_gives_no_support():
    provider, result = brand_research(BRAND_URL, [NEUTRAL_WIKI], {WIKI_URL: RETAILER_PAGE})
    assert provider.extracted and result.evidence == []
    assert_not_brand_direct(*run(BRAND_URL, [], extra=result.evidence))


def test_reference_snippet_alone_is_not_enough_the_page_lead_is_needed():
    # A reference snippet that supports but has no lead (the page could not be read).
    snippet = identity(WIKI_URL, "Its official website is lelabofragrances.com.", lead=None)
    assert_not_brand_direct(*run(BRAND_URL, [], extra=[snippet]))


def test_reference_extract_only_for_curated_hosts_and_never_the_seller():
    records = [SourceRecord("https://www.vogue-synthetic.com/x", "", "Le Labo review", NOW),
               SourceRecord("https://www.lelabofragrances.com/", "", "Le Labo home", NOW)]
    provider, result = brand_research(BRAND_URL, records, {})
    assert provider.extracted == [] and result.evidence == []


@pytest.mark.parametrize("row", ["| Website | <https://www.lelabofragrances.com.evil.io> |",
                                 "| Website | lelabofragrances.co |", "| Founded | lelabofragrances.com |",
                                 "| Website | not lelabofragrances.com |"])
def test_website_rows_need_the_exact_key_in_the_website_field(row):
    assert brand_direct.classify_excerpt(row, "www.lelabofragrances.com") == "neutral"


# ------------------------------------------------------------------ Wikipedia-only fallback search

LOOKALIKE_WIKI_RESULT = SourceRecord("https://lelabo-outlet-sale.com/wiki", "", "Le Labo outlet", NOW)


def fallback_research(listing, first, wiki, pages):
    provider = ExtractingProvider(first, pages)
    provider.wiki_records = wiki
    return provider, asyncio.run(SellerResearch(provider).brand_direct_with_status(plan_for(listing)))


def test_fallback_runs_only_without_a_reference_result_and_uses_the_fixed_query():
    first = [SourceRecord("https://www.vogue-synthetic.com/x", "", "Le Labo review", NOW)]
    provider, result = fallback_research(BRAND_URL, first, [NEUTRAL_WIKI], {WIKI_URL: WIKI_PAGE})
    assert provider.queries == ['"lelabofragrances.com" official website'] * 2
    assert provider.filters == [(), ("wikipedia.org",)]
    assert provider.extracted == [([WIKI_URL], True, "reference_page")]
    assessment, sms = run(BRAND_URL, [], extra=result.evidence)
    assert assessment.seller_risk == "LOWER_RISK"
    report = result.report()
    assert report.records_received == report.records_retained + report.records_filtered
    # A reference result in the first search: no fallback call.
    provider, _ = fallback_research(BRAND_URL, [NEUTRAL_WIKI], [NEUTRAL_WIKI], {WIKI_URL: WIKI_PAGE})
    assert provider.filters == [()]


def test_fallback_results_need_a_reference_host_and_the_same_checks():
    # Non-Wikipedia hosts in the fallback answer are ignored (the filter is not trusted).
    provider, result = fallback_research(BRAND_URL, [], [LOOKALIKE_WIKI_RESULT], {})
    assert provider.extracted == [] and result.evidence == []
    # A retailer lead on the fallback page gives nothing.
    _, result = fallback_research(BRAND_URL, [], [NEUTRAL_WIKI], {WIKI_URL: RETAILER_PAGE})
    assert result.evidence == []


@pytest.mark.parametrize("listing", ["https://lelabo-outlet-sale.com/x", "https://lelabofragrances.co/x",
                                     "https://www.lelabofragrances.com.au/x", "https://bluemercury.com/products/x"])
def test_fallback_wikipedia_page_never_helps_lookalikes_or_retailers(listing):
    _, result = fallback_research(listing, [], [NEUTRAL_WIKI], {WIKI_URL: WIKI_PAGE})
    assert result.evidence == []
    assert_not_brand_direct(*run(listing, [], extra=result.evidence))


def test_fallback_failure_is_silent_and_conservative():
    class Failing(ExtractingProvider):
        async def search_with_status(self, query, include_domains=()):
            if include_domains:
                from app.research.provider import ResearchUnavailable
                raise ResearchUnavailable("down")
            return await super().search_with_status(query)
    provider = Failing([], {})
    result = asyncio.run(SellerResearch(provider).brand_direct_with_status(plan_for(BRAND_URL)))
    assert result.evidence == [] and result.status == "empty"


def test_tavily_search_sends_include_domains_only_when_given_and_validates_it():
    import httpx, json as _json
    from app.research.provider import ResearchUnavailable
    from app.services.tavily import TavilyProvider
    bodies = []

    def handler(request):
        bodies.append(_json.loads(request.content))
        return httpx.Response(200, json={"results": []})
    provider = TavilyProvider("fixture", transport=httpx.MockTransport(handler))
    asyncio.run(provider.search_with_status("q"))
    asyncio.run(provider.search_with_status("q", include_domains=("wikipedia.org",)))
    assert "include_domains" not in bodies[0] and bodies[1]["include_domains"] == ["wikipedia.org"]
    for bad in (["wikipedia.org"], ("https://evil.example",), ("a.org", "b.org", "c.org", "d.org"), ("",)):
        with pytest.raises(ResearchUnavailable):
            asyncio.run(provider.search_with_status("q", include_domains=bad))


# ------------------------------------------------------------------ reply citation slot

def brand_sheet(n_rows=5, quote_len=160):
    from app.models import PromiseSheet
    sources = [{"source_id": f"s{i}", "url": f"https://www.lelabofragrances.com/policy-{i}.html",
                "retrieved_at": NOW.isoformat(), "content": "x" * quote_len, "content_kind": "merchant_page",
                "seller_domain": "lelabofragrances.com"} for i in range(3)]
    topics = ["return_cost", "returns", "shipping_origin", "processing_time", "transit_time"][:n_rows]
    records = [{"topic": t, "status": "supported_as_statement", "merchant_statement": "x" * quote_len,
                "explanation": "Merchant statement.", "quotes": [{"source_id": f"s{i % 3}", "quote": "x" * quote_len}]}
               for i, t in enumerate(topics)]
    return PromiseSheet.model_validate({"seller_domain": "lelabofragrances.com", "sources": sources, "records": records})


@pytest.mark.parametrize("rows,quote_len", [(1, 40), (5, 40), (5, 160), (5, 400)])
def test_brand_direct_reply_always_keeps_its_reference_link(rows, quote_len):
    assessment, _ = run(BRAND_URL, GOOD)
    assessment = assessment.model_copy(update={"promise_sheet": brand_sheet(rows, quote_len)})
    sms = format_sms(assessment)
    assert f"Brand-store reference (unverified): {GOOD[0][0]}" in sms
    assert len(sms) <= 1000
    links = re.findall(r"https?://\S+", sms)
    assert len(set(links)) <= 2
    assert sms.index("Brand-store reference") < (sms.index("Merchant statement") if "Merchant statement" in sms else len(sms))


def test_non_brand_direct_replies_keep_previous_link_rules():
    assessment, _ = run("https://lelabo-outlet-sale.com/x", GOOD)
    sheet = brand_sheet(5, 40).model_copy(update={"seller_domain": "lelabo-outlet-sale.com"})
    sms = format_sms(assessment.model_copy(update={"promise_sheet": sheet}))
    assert "Brand-store reference" not in sms and "Verify authorization" in sms
