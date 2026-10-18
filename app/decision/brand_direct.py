"""Brand-direct rule: is the listing on the brand's own official site?

Deterministic and conservative. A listing's site counts as the brand's official
store only when at least MIN_INDEPENDENT_SOURCES distinct registrable domains,
none of them the seller's own site, a sibling of it, a marketplace or a
user-generated-content host, publish text in which the listing's exact
registrable domain appears within a short window of an "official site/store"
phrase, with no warning or denial wording in that window. Any independent
source that names a different domain as official, and never the listing's,
blocks the rule.

What it establishes: the shopper is on the brand's own site, not on a
lookalike or a marketplace. What it never establishes: product authenticity,
fulfillment, or authorization of any other seller. Retrieved text is untrusted
data and is only pattern-matched here, never followed or executed. The
decision layer re-runs this check on the evidence it receives, so a label set
upstream cannot grant brand-direct status by itself.
"""
import re
import unicodedata
from dataclasses import dataclass, field

from app.models import Evidence


MIN_INDEPENDENT_SOURCES = 2
WINDOW = 160  # characters either side of a domain mention or "official" phrase

# Listings on these registrable-domain labels are marketplaces or shared hosting
# platforms: the page may belong to any third-party seller, so the site being
# "official" says nothing about who sells the item.
_MARKETPLACE_OR_PLATFORM_LABELS = frozenset("""
    amazon ebay walmart etsy aliexpress alibaba temu shein wish mercari poshmark depop
    rakuten shopee lazada flipkart taobao tmall jd craigslist offerup grailed stockx goat
    vinted vestiairecollective therealreal facebook instagram tiktok bonanza newegg
    myshopify shopify wixsite wix squarespace square bigcartel weebly webflow
    github gitlab netlify vercel herokuapp pages blogspot wordpress tumblr carrd
    google sites linktr linktree
""".split())

# Sources on these labels never count as independent confirmation: anyone can
# post there (forums, social media, reviews, Q&A, blogs) or third-party sellers
# write the text (marketplaces).
_USER_CONTENT_LABELS = _MARKETPLACE_OR_PLATFORM_LABELS | frozenset("""
    reddit quora medium substack twitter x youtube pinterest linkedin threads
    trustpilot sitejabber yelp tripadvisor discord telegram fandom
    basenotes fragrantica parfumo answers stackexchange
""".split())

_OFFICIAL = re.compile(
    r"\bofficial\s+(?:[\w'’-]+\s+){0,2}?(?:web\s*site|site|store|e-?shop|shop|online\s+store|"
    r"online\s+shop|online\s+boutique|boutique|home\s*page|page)\b", re.IGNORECASE)
_DENIAL = re.compile(
    r"\bun-?official\b|\bnot\s+(?:the|an|a|their|its)?\s*official\b|\b(?:isn't|isn’t|is\s+not|aren't|are\s+not)\b"
    r"|\bnot\s+affiliated\b|\bno\s+affiliation\b|\bfake\b|\bscam|\bfraud|\bcounterfeit|\bphish|\bimpersonat"
    r"|\blook-?\s?alike|\bcopy-?cat|\bimitat|\bbeware\b|\bwarning\b|\bclone\b|\bknock-?off",
    re.IGNORECASE)
# Domain-like tokens: labels of letters/digits/hyphens joined by dots, ending
# in an alphabetic TLD.
_DOMAIN_TOKEN = re.compile(r"(?<![\w.-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24})(?![\w-]|\.[\w-])",
                           re.IGNORECASE)


def _site(host: str | None) -> str:
    from app.decision.rules import registrable_domain
    return registrable_domain(host)


def _label(site: str) -> str:
    return site.split(".", 1)[0]


def _collapse(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_text.lower())


def _related(a: str, b: str) -> bool:
    """Collapsed names where one contains the other (shorter side >= 4 chars)."""
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 4 and short in long_


def listing_eligible(listing_host: str) -> bool:
    """Marketplaces, hosting platforms and IP literals are never brand-direct."""
    site = _site(listing_host)
    label = _label(site)
    return bool(site) and "." in site and not label.isdigit() and label not in _MARKETPLACE_OR_PLATFORM_LABELS


def is_independent(source_host: str | None, listing_site: str) -> bool:
    source_site = _site(source_host)
    if not source_site or source_site == listing_site:
        return False
    source_label, listing_label = _label(source_site), _label(listing_site)
    if source_label in _USER_CONTENT_LABELS:
        return False
    # The brand's regional siblings (brand.com.au for brand.com) and sites built
    # around the brand's name (brand-reviews.net) are not independent of it.
    return not _related(_collapse(source_label), _collapse(listing_label))


def _mentions(text: str, site: str) -> list[re.Match]:
    pattern = r"(?<![\w.-])(?:[a-z0-9-]+\.)*" + re.escape(site) + r"(?![\w-]|\.[\w-])"
    return list(re.finditer(pattern, text, re.IGNORECASE))


def _window(text: str, start: int, end: int) -> str:
    return text[max(0, start - WINDOW):end + WINDOW]


def classify_excerpt(excerpt: str, listing_site: str) -> str:
    """'supports', 'conflicts' or 'neutral' for one independent source's text."""
    from app.decision.sms import _real_tld
    for match in _mentions(excerpt, listing_site):
        window = _window(excerpt, match.start(), match.end())
        if _OFFICIAL.search(window) and not _DENIAL.search(window):
            return "supports"
    listing_label = _collapse(_label(listing_site))
    for official in _OFFICIAL.finditer(excerpt):
        window = _window(excerpt, official.start(), official.end())
        if _DENIAL.search(window) or _mentions(window, listing_site):
            continue
        for token in _DOMAIN_TOKEN.findall(window):
            if not _real_tld(token.rsplit(".", 1)[-1]):
                continue  # prose such as "Labo.Santal", not a domain
            other = _collapse(_label(_site(token)))
            # A differently named domain called official contradicts the listing;
            # same-name domains (regional siblings or lookalikes) are not a
            # contradiction, they simply never confirm the listing.
            if other and other != listing_label and not _related(other, listing_label):
                return "conflicts"
    return "neutral"


def _same_name(brand_key: str, listing_label: str) -> bool:
    """User-stated brand vs the site's name: containment or a shared 4+ char prefix."""
    prefix = 0
    for a, b in zip(brand_key, listing_label):
        if a != b:
            break
        prefix += 1
    return brand_key in listing_label or listing_label in brand_key or prefix >= 4


@dataclass(frozen=True)
class BrandDirect:
    confirmed: bool = False
    sources: list[Evidence] = field(default_factory=list)
    supporting_sites: int = 0
    conflicting_sites: int = 0
    brand_matches: bool = False


def assess(listing_host: str, evidence: list[Evidence], brand: str | None = None) -> BrandDirect:
    """Re-check seller_identity evidence; never trusts upstream labels."""
    if not listing_eligible(listing_host):
        return BrandDirect()
    listing_site = _site(listing_host)
    support: dict[str, Evidence] = {}
    conflict: set[str] = set()
    for record in evidence:
        if record.finding != "seller_identity" or not record.excerpt:
            continue
        if not is_independent(record.source_url.host, listing_site):
            continue
        verdict = classify_excerpt(record.excerpt, listing_site)
        source_site = _site(record.source_url.host)
        if verdict == "supports":
            support.setdefault(source_site, record)
        elif verdict == "conflicts":
            conflict.add(source_site)
    conflict -= set(support)
    brand_key = _collapse(brand or "")
    listing_label = _collapse(_label(listing_site))
    if brand_key and not _same_name(brand_key, listing_label):
        # The user named a brand that is not the site's own name, e.g. a Le Labo
        # product on a department store: the store being official proves nothing
        # about selling another brand's goods.
        return BrandDirect(supporting_sites=len(support), conflicting_sites=len(conflict))
    confirmed = len(support) >= MIN_INDEPENDENT_SOURCES and not conflict
    return BrandDirect(confirmed=confirmed, sources=list(support.values()) if confirmed else [],
                       supporting_sites=len(support), conflicting_sites=len(conflict),
                       brand_matches=bool(brand_key) and confirmed)
