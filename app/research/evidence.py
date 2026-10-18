"""Conservative evidence normalization; snippets never prove authorization.

Retrieved text stays quoted data. No instruction or model-generated claim is run.
"""
import asyncio
import re
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

    async def brand_direct_with_status(self, plan) -> ResearchResult:
        """One fixed-query search for independent pages naming the listing's site official.

        Results become seller_identity search snippets, never verified facts;
        app/decision/brand_direct re-checks them deterministically. Pages on the
        seller's own registrable domain are dropped here and ignored there.
        """
        from app.decision.brand_direct import listing_eligible
        from app.decision.rules import registrable_domain
        if not plan.product_url or plan.requires_user_input or plan.intent != "evaluate_purchase":
            return ResearchResult([], "skipped")
        # Only the domain name goes to the fixed search provider; the merchant
        # URL is never fetched here, so no second DNS resolution is needed.
        # The workflow skips this query when seller research found the URL unsafe.
        try:
            host = urlsplit(public_url(str(plan.product_url))).hostname
        except (UnsafeURL, ValueError):
            return ResearchResult([], "unsafe_url")
        site = registrable_domain(host)  # query text only; granting uses brand_direct.grant_key
        if not listing_eligible(host):
            return ResearchResult([], "skipped")
        # Backend-built query from the listing's registrable domain only; no
        # model-extracted text (brand, task query) reaches the provider.
        query = f'"{site}" official website'
        try:
            async with asyncio.timeout(10):
                if hasattr(self.provider, "search_with_status"):
                    response = await self.provider.search_with_status(query)
                    records, received = response.records, response.records_received
                else:
                    records = await self.provider.search(query)
                    received = min(len(records), 5)
        except ResearchUnavailable as exc:
            return ResearchResult([], "timeout" if exc.reason == "timeout" else "unavailable", provider_called=True)
        except TimeoutError:
            return ResearchResult([], "timeout", provider_called=True)
        from app.decision.brand_direct import classify_excerpt, is_independent, is_reference
        records = list(records[:5])
        if not any(_reference_host(r, is_reference) for r in records):
            # Fallback (controller decision 2026-10-17): the general search often
            # returns no reference page. One more fixed search, same query,
            # restricted to Wikipedia; still no model or user text. Its results
            # only feed the reference-page check below, never grant by themselves.
            fallback = await self._wikipedia_fallback(query)
            records = records + [r for r in fallback if _reference_host(r, is_reference)]
        evidence, seen = [], set()
        for record in records:
            try:
                source = public_url(record.source_url)
            except (UnsafeURL, ValueError):
                continue
            excerpt = record.excerpt[:2000]
            # Keep only independent pages that bear on the site's official status.
            if (source in seen or not is_independent(urlsplit(source).hostname, host)
                    or classify_excerpt(excerpt, host) == "neutral"):
                continue
            seen.add(source)
            evidence.append(Evidence(
                claim=("Unverified search excerpt about the site's official status: " + excerpt)[:1000],
                source_url=source, source_title=record.title or None, excerpt=excerpt,
                retrieved_at=record.retrieved_at, seller_domain=host.lower().rstrip(".").removeprefix("www."),
                evidence_type="search_snippet", claim_status="unknown",
                finding="seller_identity", polarity="neutral", data_mode="partial"))
        reference = await self._reference_page_support(records, host, seen)
        if reference is not None:
            # The page span replaces that URL's snippet so counts stay per record.
            evidence = [reference] + [e for e in evidence if str(e.source_url) != str(reference.source_url)]
        evidence = evidence[:5]
        received = min(5, max(received, len(evidence)))
        status = "partial" if evidence else "filtered" if received else "empty"
        return ResearchResult(evidence, status, provider_called=True, records_received=received,
                              records_filtered=received - len(evidence))

    async def _wikipedia_fallback(self, query):
        if not hasattr(self.provider, "search_with_status"):
            return []
        try:
            async with asyncio.timeout(10):
                response = await self.provider.search_with_status(query, include_domains=("wikipedia.org",))
        except (ResearchUnavailable, TimeoutError, TypeError):
            return []
        return list(response.records[:5])

    async def _reference_page_support(self, records, host, seen) -> Evidence | None:
        """Read one returned reference page (e.g. Wikipedia) through the fixed Extract API.

        Search snippets rarely include an infobox, so when no reference source
        already supports the listing, the first returned reference-source URL is
        extracted as markdown (link targets kept, so "[Official website](https://...)"
        shows its domain). Only the single line that names the listing's site as
        official is kept, as an exact span of retrieved text; the decision layer
        re-checks it. Any provider failure just means no reference support.
        """
        from app.decision.brand_direct import (_LEAD_LINE, classify_excerpt, is_independent, is_reference,
                                               lead_describes_brand)
        if not hasattr(self.provider, "extract_sources"):
            return None
        candidates = []
        for record in records:
            try:
                source = public_url(record.source_url)
            except (UnsafeURL, ValueError):
                continue
            source_host = urlsplit(source).hostname
            if is_reference(source_host) and is_independent(source_host, host):
                candidates.append((source, record))
        if not candidates:
            return None
        source, record = candidates[0]
        try:
            pages = await self.provider.extract_sources([source], markdown=True, max_chars=40000,
                                                        content_kind="reference_page")
        except ResearchUnavailable:
            return None
        for page in pages:
            text = page.excerpt
            row = next((m for m in re.finditer(r"[^\n]+", text)
                        if classify_excerpt(m.group(), host) == "supports"), None)
            lead = _LEAD_LINE.search(text)
            if row is None or lead is None:
                continue
            lead_end = text.find("\n", lead.start())
            lead_end = len(text) if lead_end < 0 else lead_end
            # One exact contiguous span covering the website row and the lead
            # sentence, so policy can re-check both from the same retrieved text.
            excerpt = text[min(row.start(), lead.start()):max(row.end(), lead_end)].strip()
            if excerpt and len(excerpt) <= 3000 and lead_describes_brand(excerpt):
                return Evidence(
                        claim=("Unverified reference page line about the site's official status: " + excerpt)[:1000],
                        source_url=source, source_title=record.title or None, excerpt=excerpt,
                        retrieved_at=page.retrieved_at, seller_domain=host.lower().rstrip(".").removeprefix("www."),
                        evidence_type="search_snippet", claim_status="unknown",
                        finding="seller_identity", polarity="neutral", data_mode="partial")
        return None


def _reference_host(record, is_reference) -> bool:
    try:
        return is_reference(urlsplit(public_url(record.source_url)).hostname)
    except (UnsafeURL, ValueError):
        return False
