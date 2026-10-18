"""Bounded SMS body; carrier encoding and segment counts need live verification."""
import re

from app.decision.rules import URL_REQUEST
from app.models import Assessment, Decision


# Merchant text is untrusted. Messaging apps turn scheme URLs, "www." hosts and
# bare domains into tappable links, so any link-like token inside a quoted
# merchant span or condition is neutralized; only the labeled source URLs that
# the formatter appends may be clickable (QA-02).
#
# Bare domains are neutralized only when they end in a real top-level domain
# (human decision, QA-08): a built-in list of common generic TLDs, every
# two-letter ASCII code (treated as a ccTLD), punycode "xn--" labels and
# all-Unicode TLDs such as ".рф". Labels may be Unicode (IDN homoglyphs) and the
# ideographic/fullwidth dots count as dots. So "2-3 days.Free returns",
# "Dr.Smith" and "No.5" survive. Accepted residual false positives: prose whose
# suffix happens to be a real TLD, e.g. "Haus.de Edition" (.de) or "50ml.It ships"
# (.it), is still replaced; safety wins over prose fidelity.
_GENERIC_TLDS = frozenset("""
    com net org edu gov mil int info biz name pro mobi asia tel travel jobs aero coop museum
    shop store online site website xyz top club vip live life world today tech dev app page
    link click blog news space fun icu buzz cloud one io co me tv ly ai gg cc
    art design beauty fashion boutique deals sale market luxury gift gifts cheap discount
    bargains coupons promo best love ltd inc llc company center email network digital media
    studio agency group global work zone run email support services solutions express
    help fit win bid trade guru rocks host press social chat host lol wtf moe
""".split())
_DOT = r"[.\u3002\uff0e\uff61]"  # ASCII, ideographic, fullwidth, halfwidth dots
_LINKISH = re.compile(
    r"(?P<always>[a-z][a-z0-9+.-]*://\S+"                       # any scheme URL
    r"|\bwww" + _DOT + r"\S+"                                    # www. host
    r"|\b(?:mailto|tel|sms|facetime|javascript|data):\S+"       # schemes without //
    r"|\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?(?:[/?#]\S*)?)"         # IPv4 literal, optional port/path
    r"|(?P<domain>\b(?:[\w-]+" + _DOT + r")+(?P<tld>[\w-]+)\b)(?P<rest>(?::\d+)?(?:[/?#]\S*)?)",
    re.IGNORECASE)
LINK_REMOVED = "[link removed]"


def _real_tld(label: str) -> bool:
    tld = label.casefold()
    if tld.startswith("xn--"):
        return True
    if tld.isascii():
        return tld in _GENERIC_TLDS or (len(tld) == 2 and tld.isalpha())
    return all(not ch.isascii() for ch in tld)  # Unicode TLD such as "рф"


def _replace(match: re.Match) -> str:
    if match.group("always"):
        return LINK_REMOVED
    host = match.group("domain")
    if _real_tld(match.group("tld")) or "xn--" in host.casefold():
        return LINK_REMOVED
    # Not a real TLD: keep the text, but still scan what followed it, so
    # "days.Free/phish.com" cannot hide a domain in a pseudo-path.
    return host + neutralize_links(match.group("rest"))


def neutralize_links(text: str) -> str:
    return _LINKISH.sub(_replace, text)


def format_sms(assessment: Assessment, max_chars: int = 1000) -> str:
    if max_chars < 350:
        raise ValueError("At least 350 characters required for policy and uncertainty")
    labels = {Decision.CONSIDER_BUYING: "Consider buying after checking listing and return terms.",
              Decision.AVOID: "Avoid this purchase: substantial adverse findings.",
              Decision.VERIFY_FIRST: "Seller authorization unconfirmed. Verify authorization and return terms before buying.",
              Decision.NEED_MORE_INFORMATION: "Send the product listing URL and product context."}
    if assessment.decision == Decision.NEED_MORE_INFORMATION and URL_REQUEST not in assessment.missing_information:
        # The user supplied a URL, but extraction was unavailable, timed out or
        # returned invalid output: do not ask for the URL again (Q2).
        labels[Decision.NEED_MORE_INFORMATION] = "The check could not be completed; no seller conclusion was established. Please try again later."
    prefix = "[SYNTHETIC/MOCK] " if assessment.data_mode == "mock" else "[PARTIAL DATA] " if assessment.data_mode == "partial" else ""
    text = f"{prefix}{assessment.seller_risk.value}: {labels[assessment.decision]} Product authenticity is not established."
    statuses = {report.status for report in assessment.research}
    notice = (" Research timed out." if "timeout" in statuses else
              " Research unavailable." if "unavailable" in statuses else
              " Listing destination could not be safely resolved." if "unsafe_url" in statuses else
              " Returned sources did not match the seller or failed validation." if "filtered" in statuses and not assessment.evidence else
              " Search returned no seller sources." if "empty" in statuses and not assessment.evidence else "")
    if len(text + notice) <= max_chars:
        text += notice
    # Promise conditions precede generic source references. Full quotes remain in
    # the shared sheet; quote/link pairs are atomic in the bounded phone body.
    promise_urls = set()
    if assessment.promise_sheet:
        sheet = assessment.promise_sheet
        registry = {source.source_id: source for source in sheet.sources}
        order = {"return_cost": 0, "returns": 1, "shipping_origin": 2, "arrival": 3,
                 "processing_time": 4, "transit_time": 5}
        # Quoted rows first, so the bounded body spends its space on what the
        # merchant actually stated rather than on unavailable checks.
        quoted_first = lambda r: (r.status in {"not_disclosed", "unavailable"}, order.get(r.topic, 10))
        for row in sorted(sheet.records, key=quoted_first):
            label = row.topic.replace("_", " ")
            if row.status == "not_disclosed":
                detail = f" {label}: not disclosed in inspected source(s)."
            elif row.status == "unavailable":
                detail = f" {label}: check unavailable."
            else:
                qualifier = "Potentially differing terms; compare conditions" if row.status == "conflicting" else "Merchant statement" if row.status == "supported_as_statement" else "Corroborated statement"
                conditions = "; ".join(neutralize_links(v) for v in row.conditions.model_dump().values() if v)
                detail = f" {qualifier} ({label}" + (f"; {conditions}" if conditions else "") + "):"
                for quote in row.quotes:
                    source = registry.get(quote.source_id)
                    if source:
                        detail += f' "{neutralize_links(quote.quote)}" {source.url}'
                detail += " Fulfillment unverified."
            row_urls = {str(registry[q.source_id].url) for q in row.quotes if q.source_id in registry}
            if len(promise_urls | row_urls) <= 2 and len(text + detail) <= max_chars:
                text += detail
                promise_urls.update(str(registry[q.source_id].url) for q in row.quotes if q.source_id in registry)
    # Source URLs are added atomically, never truncated into misleading citations.
    added = set(promise_urls)
    for record in assessment.evidence:
        if len(added) >= 2:
            break
        url = str(record.source_url)
        if url in added:
            continue
        label = " Source: " if record.claim_status == "verified_fact" else " Unverified source: "
        candidate = text + label + url
        if len(candidate) <= max_chars:
            text = candidate
            added.add(url)
        if len(added) == 2:
            break
    if assessment.evidence and not added:
        notice = " Source links exceed message length."
        if len(text + notice) <= max_chars:
            text += notice
    return text
