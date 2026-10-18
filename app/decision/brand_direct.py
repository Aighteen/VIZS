"""Brand-direct rule: is the listing on the brand's own official site?

Deterministic and conservative (threat model: docs/reviews/BRAND_DIRECT_THREAT_MODEL.md
cases C1-C15). The listing's site counts as the brand's own store only when:

1. The listing host is eligible: not a marketplace, multi-brand retailer or
   shared hosting platform, not an IP literal (C4, C5).
2. Its grant key is exact. The key is the registrable domain only when that
   domain sits under a vetted suffix (a known multi-label suffix, or a plain
   TLD whose second label is not a generic word such as "net" in "net.ph");
   otherwise it is the exact host. Over-inclusive registrable domains are safe
   for exclusion only, never for granting (C2, C4, C10).
3. Retrieved text from a curated reference source (REFERENCE_SOURCES, e.g. a
   Wikipedia infobox "Official website" link) names that exact key in the same
   clause as an "official site/store" phrase, or in a labeled "Website" field
   (an infobox row), with no denial or warning wording (C1, C3, C7, C10). Agreement among any number of
   unvetted pages is never enough on its own; such pages only add citations.
4. Every counted source is independent: not on the seller's registrable
   domain or a brand-named sibling, not a forum, social, review or
   marketplace host (C6). Distinct sources are counted per registrable domain.
5. No independent source names a different domain as official (conflict).
6. A brand the user stated, if any, matches the site's name (C9). The brand is
   only ever a blocker; it never builds a query or grants status (C8).

What it establishes: the listing is on the brand's own site per cited sources.
Never product authenticity, fulfillment, or authorization of other sellers.
Retrieved text is untrusted data, only pattern-matched here. The decision layer
re-runs this check on the evidence it receives; upstream labels grant nothing.
"""
import re
import unicodedata
from dataclasses import dataclass, field

from app.models import Evidence


# Curated reference sources (C7, C15): editorially maintained registries that
# record an organization's official website. Immutable; no runtime write path.
# Checked 2026-10-17: Wikipedia infobox "Website", Wikidata property P856
# "official website", Britannica "Official Site" links.
REFERENCE_SOURCES = frozenset({"wikipedia.org", "wikidata.org", "britannica.com"})

# Listings on these registrable-domain labels may belong to any third-party
# seller (marketplaces, hosting platforms) or sell many brands (department
# stores, beauty and fashion retailers): the site being official says nothing
# about the item's brand (C4, C5).
_INELIGIBLE_LISTING_LABELS = frozenset("""
    amazon ebay walmart etsy aliexpress alibaba temu shein wish mercari poshmark depop
    rakuten shopee lazada flipkart taobao tmall jd craigslist offerup grailed stockx goat
    vinted vestiairecollective therealreal facebook instagram tiktok bonanza newegg
    sephora nordstrom ulta farfetch macys bloomingdales saksfifthavenue neimanmarcus
    selfridges harrods johnlewis target bestbuy costco zalando asos ssense mytheresa
    net-a-porter netaporter luisaviaroma lookfantastic cultbeauty dermstore notino douglas
    fragrancenet fragrancex perfumania jomashop kohls jcpenney libertylondon spacenk
    myshopify shopify wixsite wix squarespace bigcartel weebly webflow
    github gitlab netlify vercel herokuapp firebaseapp azurewebsites cloudfront
    glitch replit framer blogspot wordpress tumblr carrd google sites linktr linktree
""".split())

# Shared platforms whose label alone is too common to list above.
_INELIGIBLE_LISTING_SITES = frozenset({"shop.app", "pages.dev", "web.app", "square.site", "workers.dev",
                                       "onrender.com", "fly.dev", "surge.sh"})

# Sources on these labels never count as independent confirmation: anyone can
# post there (forums, social media, reviews, Q&A, blogs) or third-party sellers
# write the text.
_USER_CONTENT_LABELS = _INELIGIBLE_LISTING_LABELS | frozenset("""
    reddit quora medium substack twitter x youtube pinterest linkedin threads
    trustpilot sitejabber yelp tripadvisor discord telegram fandom basenotes
    answers stackexchange scamadviser scamdoc
""".split())

# Second-level words that signal an unlisted public suffix (net.ph, com.fj,
# org.ng ...): a "registrable domain" ending in one of them is really shared.
_GENERIC_SECOND_LEVEL = frozenset("""
    com net org edu gov mil int co ac or ne go ltd plc gen biz info firm ind nom sch web me
""".split())

_OFFICIAL = re.compile(
    r"\bofficial\s+(?:[\w'’&-]+\s+){0,2}?(?:web\s*site|site|store|e-?shop|shop|online\s+store|"
    r"online\s+shop|boutique|home\s*page|storefront)\b|\bofficial\s*:", re.IGNORECASE)
_DENIAL = re.compile(
    r"\bun-?official\b|\bnot\b|n['’]t\b|\bnever\b|\bno\s+longer\b|\bformer(?:ly)?\b|\bused\s+to\b"
    r"|\bno\s+affiliation\b|\bfake\b|\bscam|\bfraud|\bcounterfeit|\bphish|\bimpersonat|\blook-?\s?alike"
    r"|\bcopy-?cat|\bimitat|\bbeware\b|\bwarning\b|\balert\b|\bclone\b|\bknock-?off|\bsuspicious\b"
    r"|\bclaims?\b|\balleged",
    re.IGNORECASE)
# A labeled website field, as in a Wikipedia infobox row rendered as a table
# line ("| Website | <https://www.brand.com> |") or a "Website: brand.com" label.
# Only the field value is matched, and it must name the exact grant key.
_WEBSITE_ROW = re.compile(r"^\s*\|?\s*(?:official\s+)?web\s*-?site\s*(?:\||:)\s*(.{1,300}?)\s*\|?\s*$",
                          re.IGNORECASE)
# Clause boundaries: sentence ends followed by space, semicolons, line breaks,
# bullets and pipes. Dots inside domains are never followed by whitespace.
_CLAUSE = re.compile(r"(?<=[.!?])\s+|[;\n\r|•·]+")
_DOMAIN_TOKEN = re.compile(r"(?<![\w.-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24})(?![\w-]|\.[\w-])",
                           re.IGNORECASE)


def _normalize(host: str | None) -> str:
    return (host or "").lower().rstrip(".").removeprefix("www.")


def _site(host: str | None) -> str:
    from app.decision.rules import registrable_domain
    return registrable_domain(host)


def _label(site: str) -> str:
    return site.split(".", 1)[0]


def _collapse(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def _related(a: str, b: str) -> bool:
    """Collapsed names where one contains the other (shorter side >= 4 chars).

    Used only to EXCLUDE sources as not independent, never to grant."""
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 4 and short in long_


def listing_eligible(listing_host: str) -> bool:
    host = _normalize(listing_host)
    site = _site(host)
    label = _label(site)
    if not site or "." not in site or all(part.isdigit() for part in site.split(".")):
        return False
    return site not in _INELIGIBLE_LISTING_SITES and label not in _INELIGIBLE_LISTING_LABELS and label.replace("-", "") not in _INELIGIBLE_LISTING_LABELS


def grant_key(listing_host: str) -> tuple[str, bool]:
    """(key, subdomains_allowed). Exact host unless the registrable domain is vetted."""
    from app.decision.rules import _MULTI_LABEL_SUFFIXES
    host = _normalize(listing_host)
    site = _site(host)
    labels = site.split(".")
    vetted = ((len(labels) == 3 and ".".join(labels[1:]) in _MULTI_LABEL_SUFFIXES)
              or (len(labels) == 2 and labels[0] not in _GENERIC_SECOND_LEVEL))
    return (site, True) if vetted else (host, False)


def is_independent(source_host: str | None, listing_host: str) -> bool:
    source_site = _site(source_host)
    listing_site = _site(listing_host)
    if not source_site or source_site == listing_site:
        return False
    source_label = _label(source_site)
    if source_label in _USER_CONTENT_LABELS or source_site in _INELIGIBLE_LISTING_SITES:
        return False
    # The brand's regional siblings (brand.com.au for brand.com) and sites built
    # around the brand's name (brand-reviews.net) are not independent of it.
    return not _related(_collapse(source_label), _collapse(_label(listing_site)))


def is_reference(source_host: str | None) -> bool:
    return _site(source_host) in REFERENCE_SOURCES


def _mentions(text: str, key: str, subdomains: bool) -> bool:
    prefix = r"(?:[a-z0-9-]+\.)*" if subdomains else r"(?:www\.)?"
    pattern = r"(?<![\w.-])" + prefix + re.escape(key) + r"(?![\w-]|\.[\w-])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def classify_excerpt(excerpt: str, listing_host: str) -> str:
    """'supports', 'conflicts' or 'neutral' for one independent source's text."""
    from app.decision.sms import _real_tld
    key, subdomains = grant_key(listing_host)
    listing_name = _collapse(_label(_site(listing_host)))
    for line in (excerpt or "").splitlines():
        # Infobox / directory row: "| Website | <https://www.brand.com> |" or "Website: brand.com".
        row = _WEBSITE_ROW.match(line)
        if row and not _DENIAL.search(row.group(1)) and _mentions(row.group(1), key, subdomains):
            return "supports"
    clauses = [c for c in _CLAUSE.split(excerpt or "") if c.strip()]
    verdict = "neutral"
    for clause in clauses:
        if not _OFFICIAL.search(clause) or _DENIAL.search(clause):
            continue
        if _mentions(clause, key, subdomains):
            return "supports"
        for token in _DOMAIN_TOKEN.findall(clause):
            if not _real_tld(token.rsplit(".", 1)[-1]):
                continue  # prose such as "Labo.Santal", not a domain
            other = _collapse(_label(_site(token)))
            # A differently named domain called official contradicts the listing.
            # Same-name domains (regional siblings, lookalikes) never confirm it
            # either, but they are not counted as a contradiction.
            if other and other != listing_name and not _related(other, listing_name):
                verdict = "conflicts"
    return verdict


# Reference-page lead sentence ("**Allbirds** is an American footwear brand ..."):
# the organization that the infobox website belongs to must be described as a
# brand or maker, and not as a retailer. Otherwise a multi-brand retailer's own
# site (live false positive 2026-10-17: a beauty retailer's Wikipedia infobox
# names its own domain) would read as the product brand's store. Strict: brands
# that describe themselves as retailers of their own goods are missed.
_LEAD_LINE = re.compile(r"^[ \t]*\*\*[^*\n]{1,120}\*\*", re.MULTILINE)
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_BRAND_WORDS = re.compile(r"\b(?:brand|manufacturer|maker|label|fashion\s+house|perfume\s+house|perfumery|"
                          r"perfumer|designer|producer)\b", re.IGNORECASE)
_RETAIL_WORDS = re.compile(r"\bretail|\bdepartment\s+stores?\b|\bchain\b|\bmarketplace|\be-?commerce\b"
                           r"|\bresell|\bdistribut|\bstockist|\bmulti-?brand|\bsupermarket|\bdrugstore|\bpharmac"
                           r"|\boutlet|\bwholesal|\bonline\s+(?:shop|store)\b|\bshopping\b|\bdealer|\bstores\s+selling"
                           r"|\bconglomerate|\bholding\s+company|\bplatform\b",
                           re.IGNORECASE)


def lead_describes_brand(excerpt: str) -> bool:
    """True when the excerpt contains a reference-page lead sentence that calls
    the subject a brand or maker and uses no retailer/marketplace wording."""
    match = _LEAD_LINE.search(excerpt or "")
    if not match:
        return False
    line = excerpt[match.start():].split("\n", 1)[0]
    plain = _MD_LINK.sub(r"\1", line).replace("**", "")
    if not re.search(r"\b(?:is|was|are)\b", plain):
        return False
    sentence = re.split(r"(?<=[.!?])\s+(?=[A-Z])", plain, maxsplit=1)[0]
    return bool(_BRAND_WORDS.search(sentence)) and not _RETAIL_WORDS.search(sentence)


def _same_name(brand_key: str, listing_name: str) -> bool:
    """User-stated brand vs the site's name: containment or a shared 4+ char prefix.

    Used only to BLOCK a mismatch (C9), never to grant."""
    prefix = 0
    for a, b in zip(brand_key, listing_name):
        if a != b:
            break
        prefix += 1
    return brand_key in listing_name or listing_name in brand_key or prefix >= 4


@dataclass(frozen=True)
class BrandDirect:
    confirmed: bool = False
    sources: list[Evidence] = field(default_factory=list)
    supporting_sites: int = 0
    conflicting_sites: int = 0
    brand_matches: bool = False


def assess(listing_host: str, evidence: list[Evidence], brand: str | None = None) -> BrandDirect:
    """Re-check seller_identity evidence; never trusts upstream labels."""
    host = _normalize(listing_host)
    if not listing_eligible(host):
        return BrandDirect()
    support: dict[str, Evidence] = {}
    conflict: set[str] = set()
    for record in evidence:
        if record.finding != "seller_identity" or not record.excerpt:
            continue
        if _normalize(record.seller_domain) != host or not is_independent(record.source_url.host, host):
            continue
        verdict = classify_excerpt(record.excerpt, host)
        source_site = _site(record.source_url.host)
        if verdict == "supports" and source_site in REFERENCE_SOURCES and not lead_describes_brand(record.excerpt):
            continue  # a reference source counts only with a brand (not retailer) lead in the same span
        if verdict == "supports":
            support.setdefault(source_site, record)
        elif verdict == "conflicts":
            conflict.add(source_site)
    conflict -= set(support)
    result = dict(supporting_sites=len(support), conflicting_sites=len(conflict))
    brand_key = _collapse(brand or "")
    if brand_key and not _same_name(brand_key, _collapse(_label(_site(host)))):
        return BrandDirect(**result)
    # A curated reference source must name the site (C7); other independent
    # pages only add citations. Agreement among unvetted pages never suffices.
    confirmed = not conflict and any(site in REFERENCE_SOURCES for site in support)
    if not confirmed:
        return BrandDirect(**result)
    # Reference source first so the phone reply cites it.
    sources = sorted(support.values(), key=lambda e: not is_reference(e.source_url.host))
    return BrandDirect(confirmed=True, sources=sources, brand_matches=bool(brand_key), **result)
