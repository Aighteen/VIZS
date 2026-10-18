"""Conservative evidence normalization; snippets never prove authorization.

Retrieved text stays quoted data. No instruction or model-generated claim is run.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit

from app.models import Evidence, ResearchReport
from app.research.provider import ResearchUnavailable, SearchProvider, SourceRecord
from app.research.url_safety import UnsafeURL, public_url, validate_public_destination


def claim_supported(claim: str, record: SourceRecord) -> bool:
    """Only literal excerpt support, not semantic entailment or factual truth."""
    return bool(claim.strip()) and claim.strip() in record.excerpt


def normalize_record(record: SourceRecord, seller_domain: str) -> Evidence | None:
    """Require exact seller domain mention or first-party host; avoid name collisions.

    Brand/region is not extracted reliably from a URL alone. Authorization and
    jurisdiction remain unknown; this layer never emits verified_fact.
    """
    import re
    url = public_url(record.source_url)
    source_host = urlsplit(url).hostname.lower().removeprefix("www.")
    seller_domain = seller_domain.lower().removeprefix("www.")
    domain_pattern = r"(?<![\w.-])" + re.escape(seller_domain) + r"(?![\w.-])"
    if source_host != seller_domain and not re.search(domain_pattern, record.excerpt, re.IGNORECASE):
        return None
    excerpt = record.excerpt[:2000]
    if not excerpt.strip():
        return None
    return Evidence(claim=("Unverified search excerpt: " + excerpt)[:1000], source_url=url,
                    source_title=record.title or None, excerpt=excerpt,
                    retrieved_at=record.retrieved_at, seller_domain=seller_domain,
                    evidence_type="search_snippet", claim_status="unknown",
                    finding="other", polarity="neutral", data_mode="partial")


@dataclass(frozen=True)
class ResearchResult:
    evidence: list[Evidence]
    status: Literal["partial", "empty", "filtered", "unavailable", "timeout", "unsafe_url", "skipped"]
    provider_called: bool = False
    records_received: int = 0
    records_filtered: int = 0
    data_mode: str = "partial"
    source_records: list[SourceRecord] = field(default_factory=list)
    uncertainty: str = "Search snippets are unverified; authorization, brand and region remain unconfirmed."

    def report(self) -> ResearchReport:
        return ResearchReport(status=self.status, provider_called=self.provider_called,
                              records_received=self.records_received,
                              records_retained=len(self.evidence), records_filtered=self.records_filtered)


class SellerResearch:
    """One provider call per permitted task; no mutable per-request status.

    All results are partial because search snippets are not independently
    verified. Empty results honestly mean no usable evidence, not seller fraud.
    A caps total task invocations; this callable caps each invocation to one call.
    """
    def __init__(self, provider: SearchProvider, *, destination_validator=validate_public_destination):
        self.provider = provider
        self.destination_validator = destination_validator

    async def __call__(self, plan, task) -> list[Evidence]:
        return (await self.research_with_status(plan, task)).evidence

    async def research_with_status(self, plan, task) -> ResearchResult:
        if task.kind != "verify_seller" or not plan.product_url or plan.requires_user_input:
            return ResearchResult([], "skipped")
        try:
            url = await self.destination_validator(str(plan.product_url))
        except UnsafeURL:
            return ResearchResult([], "unsafe_url")
        domain = urlsplit(url).hostname
        # Backend constructs the query; model-suggested query/instructions ignored.
        query = f'"{domain}" seller authorization return policy complaints'
        try:
            async with asyncio.timeout(10):
                if hasattr(self.provider, "search_with_status"):
                    response = await self.provider.search_with_status(query)
                    records = response.records
                    received = response.records_received
                else:
                    records = await self.provider.search(query)
                    received = min(len(records), 5)
        except ResearchUnavailable as exc:
            return ResearchResult([], "timeout" if exc.reason == "timeout" else "unavailable", provider_called=True)
        except TimeoutError:
            return ResearchResult([], "timeout", provider_called=True)
        evidence = []
        seen = set()
        for record in records[:5]:
            try:
                item = normalize_record(record, domain)
            except (UnsafeURL, ValueError):
                continue
            if item and str(item.source_url) not in seen:
                seen.add(str(item.source_url))
                evidence.append(item)
        status = "partial" if evidence else "filtered" if received else "empty"
        return ResearchResult(evidence, status, provider_called=True,
                              records_received=received, records_filtered=received-len(evidence),
                              source_records=list(records[:5]))
