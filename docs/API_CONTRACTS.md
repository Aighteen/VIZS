# Proposed contracts — app-side Pydantic models

These are **team-owned internal interfaces**, not real Photon 2.0 payload specifications. Confirm actual Photon callback/auth/send parameters from your beta account before creating the adapter.

## HTTP endpoints

| Endpoint | Purpose | External provider dependency |
|---|---|---|
| `GET /healthz` | Basic readiness and app health, with no secrets | No |
| `POST /api/v1/evaluate` | Local direct evaluation, bypasses Photon transport but uses same core workflow | Grok + search for live mode; injected mocks for tests |
| `POST /api/v1/evaluate-message` | Loopback bridge: same evaluation, returns `{assessment, message_text}` | Same as evaluate |
| `POST /api/v1/extension/evaluate` | Extension route: same body/response as evaluate-message; bearer pairing token, origin allowlist, rate/inflight budget checked before provider work | Same as evaluate |
| `POST /api/v1/mock/messages` | Opt-in local simulator, `{event_id, text}`, labeled mock; not Photon JSON. 404 when disabled; otherwise any `Origin` -> 403, declared oversize -> 413, non-JSON -> 415 before the body is read (Q7) | None (mock transport) |
| `POST /webhooks/photon` | Implemented as a fixed 503. Future: real inbound adapter, security checks, idempotency, prompt acknowledgement | Photon 2.0 verified docs |
| `GET /api/v1/assessments/{id}` (optional) | Not implemented | Requires storage choice |

All three evaluation routes require `channel: "debug"` in the request body; `ShoppingRequest.channel` allows only `sms` and `debug`. The illustrative schema below predates the executable models in `app/models/__init__.py`, which are the source of truth.

## Internal schema candidates (illustrative; implement using Pydantic v2)

```python
from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

class Risk(str, Enum):
    LOWER_RISK = 'LOWER_RISK'
    HIGHER_RISK = 'HIGHER_RISK'
    INSUFFICIENT_EVIDENCE = 'INSUFFICIENT_EVIDENCE'

class Decision(str, Enum):
    CONSIDER_BUYING = 'CONSIDER_BUYING'
    VERIFY_FIRST = 'VERIFY_FIRST'
    AVOID = 'AVOID'
    NEED_MORE_INFORMATION = 'NEED_MORE_INFORMATION'

class ShoppingRequest(BaseModel):
    request_id: str
    message_text: str = Field(min_length=1, max_length=4000)
    channel: Literal['sms', 'debug'] = 'debug'

class ResearchTask(BaseModel):
    kind: Literal['verify_seller', 'compare_prices', 'recommend_card']
    query: str

class OrchestratorPlan(BaseModel):
    request_id: str
    intent: Literal['evaluate_purchase', 'need_more_information', 'unsupported']
    product_url: HttpUrl | None = None
    purchase_price: float | None = Field(default=None, ge=0)
    tasks: list[ResearchTask] = Field(default_factory=list)
    requires_user_input: bool = False

class Evidence(BaseModel):
    claim: str
    source_url: HttpUrl | None = None
    source_title: str | None = None
    evidence_type: Literal['official', 'directory', 'regulatory', 'investigation', 'complaint', 'community', 'unverified_review', 'missing_verification']
    claim_status: Literal['verified_fact', 'allegation', 'inference', 'unknown']
    retrieved_at: datetime | None = None

class Assessment(BaseModel):
    request_id: str
    seller_risk: Risk
    decision: Decision
    summary: str
    evidence: list[Evidence] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    data_mode: Literal['live', 'partial', 'mock']
```

**Implementation considerations:** For money, use `Decimal` rather than binary floats in the P1 card calculator; the above `purchase_price: float` is only a first-pass parsing contract to revise before financial arithmetic. Validate URL safety **beyond** `HttpUrl` (DNS/IP/resolved redirects). Validate only permitted tasks; unknown model output must fail closed into `NEED_MORE_INFORMATION`.

## Photon adapter contract (internal abstraction only)

```
parse_and_verify_inbound(raw_bytes, headers) -> VerifiedInboundMessage
  fields: external_message_id, sender_handle, channel, text, received_at
  NOTE: names are OUR normalized fields, NOT assumed Photon JSON keys.

send_text(destination, body, correlation_id) -> SendResult
  fields: provider_message_id?, accepted?, error_code?
  NOTE: determine the actual client method only after checking Photon 2.0 docs.
```

## Sample DEBUG request and illustrative response

```json
{"request_id":"req_demo_1","message_text":"Is this product legit? https://example.com/product/123 — $150","channel":"debug"}
```

```json
{"request_id":"req_demo_1","seller_risk":"INSUFFICIENT_EVIDENCE","decision":"VERIFY_FIRST","summary":"Seller authorization was not confirmed; verify before buying.","evidence":[],"missing_information":["Manufacturer-authorized seller confirmation"],"data_mode":"mock"}
```

`example.com` and all sample data are placeholders. This must never be shown as a real seller assessment.

## Error behaviors and status discipline

- Missing URL/basic product → clarification or `NEED_MORE_INFORMATION`, not invented product details.
- Unsupported/malformed Grok JSON → controlled validation failure; no fabricated research.
- Search empty/unavailable → `INSUFFICIENT_EVIDENCE` with clear missing information.
- Webhook validation failure → reject (exact status depends on documented Photon retry contract).
- Duplicate inbound → idempotent no duplicate outbound response.
- Timeout → bounded status/follow-up or explicit failure; do not leave user expecting a result if work died.

## Executable Contract gate (Packet D)

`app.models` is the executable Pydantic v2 source of truth. All contracts forbid extra fields and bound strings/collections. Money uses Decimal; evidence timestamps require timezone information. Only `verify_seller` is permitted at P0. Plan fields add optional brand, clarification, bounded status and data_mode. Evidence requires an actual source_url and retrieval timestamp; gaps are assessment missing_information, never invented source records. Evidence adds excerpt, optional evidence_id and seller_domain, explicit finding and polarity, and data_mode. Search snippets must not automatically become verified_fact.

`tests/fixtures/positive.json` and `insufficient.json` are SYNTHETIC, mock-labeled contract examples, not real research. Risk/decision combinations are validated; mock/partial evidence cannot produce a live-labeled assessment. HttpUrl syntax is not SSRF protection; C owns DNS/redirect safety.

Policy integration: `decide(request, plan, evidence) -> Assessment`; `format_sms(assessment) -> str`. Research yields `list[Evidence]`. Strong findings must refer to the listing seller via seller_domain. Official supported authorization permits LOWER_RISK; two independent regulatory/investigation substantial adverse findings permit HIGHER_RISK. Conflicting or weak records conservatively yield VERIFY_FIRST. These are prototype decision criteria, never authenticity verification.


## Research response follow-up

`Evidence.evidence_type` additionally accepts `search_snippet`. These records remain `claim_status=unknown`, neutral and non-decisive; relevant records are retained as explicitly unverified source references even when the decision remains VERIFY_FIRST. Existing risk criteria are unchanged.

`Assessment.research` is a default-empty list of up to three `ResearchReport` records. Fields: provider=tavily, status=partial/empty/filtered/unavailable/timeout/unsafe_url/skipped, provider_called, records_received, records_retained, records_filtered. Counts are bounded 0..5 per call and received=retained+filtered. Partial requires retained records; filtered requires received records and zero retained; other states contain no records. These counts describe research normalization, before policy selects its decision evidence.

`POST /api/v1/evaluate-message` is the local bridge endpoint returning `{assessment, message_text}` using the same evaluation/policy and D formatter; no Photon callback payload or authentication schema is implied. SDK inbound authentication and registered-sender admission are handled by the bounded Spectrum test listener. Developer API remains loopback-only in tests.


## Promise contract gate (completion build)

Assessment.promise_sheet is optional (default null), preserving old callers. PromiseSheet holds seller_domain, up to eight PromiseSource records and twelve PromiseRecord rows plus domain_context/image_context. Sources carry source_id, url, retrieved_at, provider-returned content (20,000 characters maximum), content_kind merchant_page/search_snippet/independent_page, seller_domain and data_mode. Records carry topic, status, merchant_statement, explanation, quotes [{source_id, quote}] and conditions {region,time,eligibility}. Statuses: supported_as_statement, independently_corroborated, conflicting, not_disclosed, unavailable. Merchant statements are not verified fulfillment. Domain context may carry registered_at; registration is not business age or fraud evidence. Image checks default unavailable.

Python gate: validate_promise_sheet(sheet, sources, seller_domain=None) -> PromiseSheet. The sources argument is REQUIRED and supplied independently by provider code, never by the model. Quotes must be exact spans of that registry; missing/unrelated sources and invented spans reject rows. Model source content is never a trust authority. decide(request, plan, evidence, promise_sheet=None) preserves existing callers. Both channels consume the same attached sheet. Synthetic fixtures promise_{supported,conflict,missing,unavailable}.json are not live research.
