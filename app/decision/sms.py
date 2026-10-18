"""Bounded SMS body; carrier encoding and segment counts need live verification."""
import re

from app.decision.rules import URL_REQUEST
from app.models import Assessment, Decision


# Merchant text is untrusted. Messaging apps turn scheme URLs, "www." hosts and
# bare domains into tappable links, so any link-like token inside a quoted
# merchant span or condition is neutralized; only the labeled source URLs that
# the formatter appends may be clickable (QA-02).
_LINKISH = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://\S+)|(?:\bwww\.\S+)|(?:\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b(?:[/?#]\S*)?)",
    re.IGNORECASE)
LINK_REMOVED = "[link removed]"


def neutralize_links(text: str) -> str:
    return _LINKISH.sub(LINK_REMOVED, text)


def format_sms(assessment: Assessment, max_chars: int = 1000) -> str:
    if max_chars < 350:
        raise ValueError("At least 350 characters required for policy and uncertainty")
    labels = {Decision.CONSIDER_BUYING: "Consider buying after checking listing and return terms.",
              Decision.AVOID: "Avoid this purchase: substantial adverse findings.",
              Decision.VERIFY_FIRST: "Seller authorization unconfirmed. Verify authorization and return terms before buying.",
              Decision.NEED_MORE_INFORMATION: "Send the fragrance listing URL and product context."}
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
        for row in sorted(sheet.records, key=lambda r: order.get(r.topic, 10)):
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
