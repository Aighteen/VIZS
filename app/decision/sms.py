"""Bounded SMS body; carrier encoding and segment counts need live verification."""
from app.models import Assessment, Decision


def format_sms(assessment: Assessment, max_chars: int = 1000) -> str:
    if max_chars < 350:
        raise ValueError("At least 350 characters required for policy and uncertainty")
    labels = {Decision.CONSIDER_BUYING: "Consider buying after checking listing and return terms.",
              Decision.AVOID: "Avoid this purchase: substantial adverse findings.",
              Decision.VERIFY_FIRST: "Seller authorization unconfirmed. Verify authorization and return terms before buying.",
              Decision.NEED_MORE_INFORMATION: "Send the fragrance listing URL and product context."}
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
    # Source URLs are added atomically, never truncated into misleading citations.
    added = set()
    for record in assessment.evidence:
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
