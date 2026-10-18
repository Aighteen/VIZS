"""Deterministic span/provenance checks, independent of model assertions."""
from app.models import PromiseConditions, PromiseRecord, PromiseSheet, PromiseSource


# A business address is not proof of shipping origin (Q4). A positive
# shipping_origin row must quote explicit origin wording.
ORIGIN_WORDING = ("ships from", "shipped from", "dispatched from", "dispatches from", "warehouse",
                  "fulfilled from", "fulfillment center", "sent from", "origin")
ORIGIN_NOT_PROVEN = "Not disclosed in inspected sources: an address is not proof of shipping origin."


def _has_origin_wording(row: PromiseRecord) -> bool:
    return any(word in q.quote.casefold() for q in row.quotes for word in ORIGIN_WORDING)


def _host(value: str) -> str:
    return value.lower().removeprefix("www.").rstrip(".")


def validate_promise_sheet(sheet: PromiseSheet, sources: list[PromiseSource], seller_domain: str | None = None) -> PromiseSheet:
    """Filter invalid rows using a separately supplied provider source registry.

    This validates quotation/provenance, not semantic truth or fulfillment. Content
    supplied by a model must never be used for the required sources argument.
    """
    sheet = PromiseSheet.model_validate(sheet)
    domain = seller_domain or sheet.seller_domain
    if not domain:
        return PromiseSheet()
    registry = {}
    urls = set()
    for raw in sources[:8]:
        source = PromiseSource.model_validate(raw)
        if _host(source.seller_domain) != _host(domain):
            continue
        if source.content_kind == "merchant_page" and _host(source.url.host) != _host(domain):
            continue
        if source.source_id in registry or str(source.url) in urls:
            continue
        registry[source.source_id] = source
        urls.add(str(source.url))
    rows, seen = [], set()
    for row in sheet.records:
        references = [registry.get(q.source_id) for q in row.quotes]
        if any(source is None or q.quote not in source.content for q, source in zip(row.quotes, references)):
            continue
        if row.merchant_statement and not any(row.merchant_statement in q.quote for q in row.quotes):
            continue
        if row.status in {"supported_as_statement", "independently_corroborated", "conflicting"} and not row.quotes:
            continue
        # A snippet is a reference, not inspected policy content.
        if row.status != "unavailable" and references and any(s.content_kind == "search_snippet" for s in references):
            continue
        if row.status == "supported_as_statement" and not any(s.content_kind == "merchant_page" for s in references):
            continue
        if row.status == "independently_corroborated":
            if not any(s.content_kind == "independent_page" and _host(s.url.host) != _host(domain) for s in references):
                continue
        if row.status == "conflicting":
            if len({(q.source_id, q.quote) for q in row.quotes}) < 2:
                continue
            # Different explicit regional scopes cannot become a global conflict.
            if row.conditions.region and any(row.conditions.region not in s.content for s in references):
                continue
        if row.status == "not_disclosed" and not any(s.content_kind == "merchant_page" for s in registry.values()):
            continue
        # Conditions must also be source spans: models cannot invent a region/time.
        content = "\n".join(s.content for s in references)
        if any(value and value not in content for value in row.conditions.model_dump().values()):
            continue
        key = (row.topic, row.status, tuple((q.source_id, q.quote) for q in row.quotes))
        if key in seen:
            continue
        seen.add(key)
        # Exact spans do not entail a model's interpretation. Only deterministic
        # expectation wording is exposed as the authoritative explanation.
        descriptions = {
            "supported_as_statement": "Merchant statement in retrieved content; fulfillment unverified.",
            "independently_corroborated": "Statement also appears in an independent retrieved source; fulfillment unverified.",
            "conflicting": "Potentially differing terms; compare the quoted conditions and applicability.",
            "not_disclosed": "Not disclosed in inspected sources.",
            "unavailable": "This check was unavailable; no conclusion was drawn.",
        }
        if (row.topic == "shipping_origin" and row.status in {"supported_as_statement", "independently_corroborated"}
                and not _has_origin_wording(row)):
            downgraded = row.model_copy(update={"status": "not_disclosed", "quotes": [], "merchant_statement": None,
                                                "conditions": PromiseConditions(),
                                                "explanation": ORIGIN_NOT_PROVEN})
            downgraded_key = (row.topic, "not_disclosed", ())
            if downgraded_key not in seen:
                seen.add(downgraded_key)
                rows.append(downgraded)
            continue
        rows.append(row.model_copy(update={"explanation": descriptions[row.status]}))
    return sheet.model_copy(update={"seller_domain": domain, "sources": list(registry.values()), "records": rows})
