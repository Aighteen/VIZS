"""Conservative deterministic prototype policy, never authenticity verification."""
from app.models import Assessment, Decision, Evidence, OrchestratorPlan, Risk, ShoppingRequest


def decide(request: ShoppingRequest, plan: OrchestratorPlan, evidence: list[Evidence]) -> Assessment:
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
        missing = ["Fragrance listing URL and product context"]
    else:
        host = plan.product_url.host.lower().removeprefix("www.")
        relevant = [e for e in records if e.seller_domain and e.seller_domain.lower().removeprefix("www.") == host]
        selected = relevant
        grounded = [e for e in relevant if e.claim_status == "verified_fact" and e.excerpt]
        authorized = [e for e in grounded if e.finding == "seller_authorized" and e.evidence_type == "official" and e.polarity == "supports"]
        adverse = [e for e in grounded if e.finding == "substantial_adverse" and e.evidence_type in {"regulatory", "investigation"} and e.polarity == "supports"]
        adverse_hosts = {e.source_url.host.lower().removeprefix("www.") for e in adverse}
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
                      summary=summary, evidence=selected, missing_information=missing, data_mode=mode)
