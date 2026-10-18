"""Shared, provider-independent contracts. URLs still require C's safety checks."""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Risk(str, Enum):
    LOWER_RISK = "LOWER_RISK"
    HIGHER_RISK = "HIGHER_RISK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Decision(str, Enum):
    CONSIDER_BUYING = "CONSIDER_BUYING"
    VERIFY_FIRST = "VERIFY_FIRST"
    AVOID = "AVOID"
    NEED_MORE_INFORMATION = "NEED_MORE_INFORMATION"


class ShoppingRequest(Contract):
    request_id: str = Field(min_length=1, max_length=128)
    message_text: str = Field(min_length=1, max_length=4000)
    channel: Literal["sms", "debug"] = "debug"


class ResearchTask(Contract):
    kind: Literal["verify_seller"]
    query: str = Field(min_length=1, max_length=500)


class OrchestratorPlan(Contract):
    request_id: str = Field(min_length=1, max_length=128)
    intent: Literal["evaluate_purchase", "need_more_information", "unsupported"]
    product_url: HttpUrl | None = None
    purchase_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    tasks: list[ResearchTask] = Field(default_factory=list, max_length=3)
    requires_user_input: bool = False
    brand: str | None = Field(default=None, max_length=120)
    clarification: str | None = Field(default=None, max_length=300)
    status: Literal["ok", "missing_input", "invalid_output", "timeout", "unavailable"] = "ok"
    data_mode: Literal["live", "partial", "mock"] = "partial"


class Evidence(Contract):
    claim: str = Field(min_length=1, max_length=1000)
    source_url: HttpUrl
    source_title: str | None = Field(default=None, max_length=300)
    evidence_type: Literal["official", "directory", "regulatory", "investigation", "complaint", "community", "unverified_review", "search_snippet"]
    claim_status: Literal["verified_fact", "allegation", "inference", "unknown"]
    retrieved_at: AwareDatetime
    excerpt: str | None = Field(default=None, max_length=3000)
    evidence_id: str | None = Field(default=None, max_length=128)
    seller_domain: str | None = Field(default=None, max_length=253)
    finding: Literal["seller_authorized", "substantial_adverse", "seller_identity", "return_policy", "discount", "authorization_unknown", "other"] = "other"
    polarity: Literal["supports", "contradicts", "neutral"] = "neutral"
    data_mode: Literal["live", "partial", "mock"] = "partial"


class ResearchReport(Contract):
    provider: Literal["tavily"] = "tavily"
    status: Literal["partial", "empty", "filtered", "unavailable", "timeout", "unsafe_url", "skipped"]
    provider_called: bool = False
    records_received: int = Field(default=0, ge=0, le=5)
    records_retained: int = Field(default=0, ge=0, le=5)
    records_filtered: int = Field(default=0, ge=0, le=5)

    @model_validator(mode="after")
    def consistent_counts(self):
        if self.records_received != self.records_retained + self.records_filtered:
            raise ValueError("Research counts disagree")
        if not self.provider_called and self.records_received:
            raise ValueError("Records require a provider call")
        if self.status == "partial" and not self.records_retained:
            raise ValueError("Partial research requires retained records")
        if self.status == "filtered" and (not self.records_received or self.records_retained):
            raise ValueError("Filtered research requires only rejected records")
        if self.status not in {"partial", "filtered"} and self.records_received:
            raise ValueError("This research status cannot contain records")
        return self


class PromiseSource(Contract):
    """Provider-returned content; never accept model-written text as source proof."""
    source_id: str = Field(min_length=1, max_length=80)
    url: HttpUrl
    title: str | None = Field(default=None, max_length=300)
    retrieved_at: AwareDatetime
    content: str = Field(min_length=1, max_length=20000)
    content_kind: Literal["merchant_page", "search_snippet", "independent_page"]
    seller_domain: str = Field(min_length=1, max_length=253)
    data_mode: Literal["live", "partial", "mock"] = "partial"


class PromiseQuote(Contract):
    source_id: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=1200)


class PromiseConditions(Contract):
    region: str | None = Field(default=None, max_length=120)
    time: str | None = Field(default=None, max_length=200)
    eligibility: str | None = Field(default=None, max_length=300)


class PromiseRecord(Contract):
    topic: Literal["shipping_origin", "processing_time", "transit_time", "arrival", "returns", "return_cost", "domain_history", "photos", "domain_registration", "photo_reuse", "ai_photo"]
    status: Literal["supported_as_statement", "independently_corroborated", "conflicting", "not_disclosed", "unavailable"]
    merchant_statement: str | None = Field(default=None, max_length=1200)
    explanation: str = Field(min_length=1, max_length=700)
    quotes: list[PromiseQuote] = Field(default_factory=list, max_length=6)
    conditions: PromiseConditions = Field(default_factory=PromiseConditions)


class PromiseContext(Contract):
    status: Literal["unavailable", "unknown", "context_only", "available"] = "unavailable"
    explanation: str = Field(default="This check is not available; no conclusion was drawn.", min_length=1, max_length=500)
    source_url: HttpUrl | None = None
    retrieved_at: AwareDatetime | None = None
    registered_at: AwareDatetime | None = None


class PromiseSheet(Contract):
    seller_domain: str | None = Field(default=None, max_length=253)
    sources: list[PromiseSource] = Field(default_factory=list, max_length=8)
    records: list[PromiseRecord] = Field(default_factory=list, max_length=12)
    domain_context: PromiseContext = Field(default_factory=PromiseContext)
    image_context: PromiseContext = Field(default_factory=PromiseContext)


class Assessment(Contract):
    request_id: str = Field(min_length=1, max_length=128)
    seller_risk: Risk
    decision: Decision
    summary: str = Field(min_length=1, max_length=500)
    evidence: list[Evidence] = Field(default_factory=list, max_length=30)
    promise_sheet: PromiseSheet | None = None
    research: list[ResearchReport] = Field(default_factory=list, max_length=3)
    missing_information: list[str] = Field(default_factory=list, max_length=10)
    data_mode: Literal["live", "partial", "mock"]

    @model_validator(mode="after")
    def consistent_decision(self):
        allowed = {Risk.LOWER_RISK: {Decision.CONSIDER_BUYING}, Risk.HIGHER_RISK: {Decision.AVOID}, Risk.INSUFFICIENT_EVIDENCE: {Decision.VERIFY_FIRST, Decision.NEED_MORE_INFORMATION}}
        if self.decision not in allowed[self.seller_risk]:
            raise ValueError("Risk and decision disagree")
        if self.data_mode == "live" and any(e.data_mode != "live" for e in self.evidence):
            raise ValueError("Non-live evidence cannot be labeled live")
        if self.data_mode == "live" and self.promise_sheet and any(s.data_mode != "live" for s in self.promise_sheet.sources):
            raise ValueError("Non-live promise sources cannot be labeled live")
        return self


class VerifiedInboundMessage(Contract):
    """Normalized internal fields; not a Photon wire specification."""
    external_message_id: str = Field(min_length=1, max_length=200)
    sender_handle: str = Field(min_length=1, max_length=200, repr=False)
    channel: Literal["sms", "imessage"]
    text: str = Field(min_length=1, max_length=4000)
    received_at: AwareDatetime


class SendResult(Contract):
    provider_message_id: str | None = Field(default=None, max_length=200)
    accepted: bool
    error_code: str | None = Field(default=None, max_length=100)
