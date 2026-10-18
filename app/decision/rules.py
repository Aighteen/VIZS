"""Conservative deterministic prototype policy, never authenticity verification."""
from app.models import Assessment, Decision, Evidence, OrchestratorPlan, Risk, ShoppingRequest, PromiseSheet


# Marks a reply that must ask the user for a listing URL. Runtime replaces it when
# the URL was supplied but extraction failed (Q2), so the phone reply never asks
# for a URL the user already sent.
URL_REQUEST = "Fragrance listing URL and product context"


# Common multi-label public suffixes. This is a deliberately small built-in list,
# not the full Public Suffix List (no new dependency). A host under a suffix not
# listed here (a private suffix such as "github.io", or a rarer second-level
# ccTLD) falls back to its last two labels. For a missed multi-label suffix that
# fallback is over-inclusive: more hosts count as the seller's own site, never
# fewer, so it can only withhold LOWER_RISK, not grant it (Q6).
_MULTI_LABEL_SUFFIXES = frozenset({
    "co.uk", "org.uk", "me.uk", "ltd.uk", "plc.uk", "net.uk", "ac.uk", "gov.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au", "asn.au", "id.au",
    "co.nz", "net.nz", "org.nz", "co.jp", "ne.jp", "or.jp", "ac.jp", "go.jp",
    "com.br", "net.br", "org.br", "com.mx", "com.ar", "com.co", "com.pe", "com.ve",
    "com.cn", "net.cn", "org.cn", "com.hk", "com.tw", "com.sg", "com.my", "com.ph",
    "co.kr", "or.kr", "co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in",
    "co.id", "co.th", "in.th", "com.vn", "com.pk", "com.bd", "com.np", "com.lk",
    "co.za", "org.za", "com.ng", "co.ke", "com.eg", "co.il", "org.il", "com.tr",
    "com.sa", "com.qa", "com.kw", "co.ae", "com.ua", "com.pl", "com.es", "com.pt",
    "com.gr", "com.ru", "co.at", "or.at", "com.de",
})


def _normalize_host(host: str | None) -> str:
    return (host or "").lower().rstrip(".").removeprefix("www.")


def registrable_domain(host: str | None) -> str:
    """Approximate registrable domain (eTLD+1) without the Public Suffix List.

    ``store.myshop.co.uk`` -> ``myshop.co.uk``; ``store.myshop.com`` -> ``myshop.com``.
    See _MULTI_LABEL_SUFFIXES for the documented limitation.
    """
    labels = [label for label in _normalize_host(host).split(".") if label]
    if labels and all(label.isdigit() for label in labels):
        return ".".join(labels)  # IPv4 literal: the whole address is the site
    if len(labels) >= 3 and ".".join(labels[-2:]) in _MULTI_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _same_site(source_host: str | None, seller_host: str) -> bool:
    """True when the source is anywhere under the seller's registrable domain:
    the seller host, its subdomains and its parent registrable domain (QA-01, Q6)."""
    source = _normalize_host(source_host)
    site = registrable_domain(seller_host)
    return bool(site) and (source == site or source.endswith("." + site))


def decide(request: ShoppingRequest, plan: OrchestratorPlan, evidence: list[Evidence], promise_sheet: PromiseSheet | None = None) -> Assessment:
    if request.request_id != plan.request_id:
        raise ValueError("Mismatched request correlation")
    records = [Evidence.model_validate(e) for e in evidence][:30]
    mode = "mock" if plan.data_mode == "mock" or any(e.data_mode == "mock" for e in records) else "partial"
    if plan.data_mode == "live" and records and all(e.data_mode == "live" for e in records):
        mode = "live"
    risk, action = Risk.INSUFFICIENT_EVIDENCE, Decision.VERIFY_FIRST
    summary = "Seller authorization remains unconfirmed. Verify authorization and return terms before buying."
    missing = ["Independent seller verification", "Product authenticity is not established."]
    selected = []
    if not plan.product_url or plan.requires_user_input or plan.intent != "evaluate_purchase":
        action = Decision.NEED_MORE_INFORMATION
        summary = "Send the fragrance listing URL so the seller can be assessed."
        missing = [URL_REQUEST]
    else:
        host = plan.product_url.host.lower().removeprefix("www.")
        relevant = [e for e in records if e.seller_domain and e.seller_domain.lower().removeprefix("www.") == host]
        selected = relevant
        grounded = [e for e in relevant if e.claim_status == "verified_fact" and e.excerpt]
        # A shop's self-asserted authorization is never manufacturer corroboration:
        # evidence hosted anywhere under the listing seller's registrable domain
        # (seller host, its subdomains, its parent domain) is excluded however it
        # is labeled (QA-01, Q6). store.brand.com + brand.com is therefore
        # VERIFY_FIRST, an accepted trade-off.
        authorized = [e for e in grounded if e.finding == "seller_authorized" and e.evidence_type == "official"
                      and e.polarity == "supports" and not _same_site(e.source_url.host, host)]
        adverse = [e for e in grounded if e.finding == "substantial_adverse" and e.evidence_type in {"regulatory", "investigation"} and e.polarity == "supports"]
        # Independence is per registrable domain: two subdomains of one site are one source (QA-09).
        adverse_hosts = {registrable_domain(e.source_url.host) for e in adverse}
        contradiction = any(e.polarity == "contradicts" for e in relevant) or bool(authorized and adverse)
        if contradiction:
            summary = "Seller evidence conflicts. Verify independently before buying."
            missing.insert(0, "Resolution of conflicting seller evidence")
        elif len(adverse_hosts) >= 2:
            risk, action = Risk.HIGHER_RISK, Decision.AVOID
            summary = "Multiple independent substantial adverse findings support higher seller risk. Avoid this purchase."
            selected = adverse
            missing = ["These findings do not establish product authenticity."]
        elif authorized and not adverse:
            risk, action = Risk.LOWER_RISK, Decision.CONSIDER_BUYING
            summary = "Official seller authorization supports lower seller risk. Consider buying after checking listing and return terms."
            selected = authorized
            missing = ["Authorization does not establish product authenticity."]
    return Assessment(request_id=request.request_id, seller_risk=risk, decision=action,
                      summary=summary, evidence=selected, missing_information=missing, data_mode=mode, promise_sheet=promise_sheet)
