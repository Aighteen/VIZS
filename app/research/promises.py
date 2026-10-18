"""Bounded provider-only policy collection, reusing seller-search records."""
import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.research.provider import SourceRecord, ResearchUnavailable
from app.research.url_safety import public_url, strip_tracking, validate_public_destination, UnsafeURL


@dataclass(frozen=True)
class PromiseSourceResult:
    records: list[SourceRecord]
    status: str
    requested: int = 0


async def collect_promise_sources(provider, plan, records=(), *, destination_validator=validate_public_destination):
    """At most one Extract call, <=3 pages. No speculative path crawling."""
    if not plan.product_url or plan.requires_user_input:
        return PromiseSourceResult([], "skipped")
    urls = []
    try:
        # Ad-tracking parameters do not select content and long ones made the
        # provider return a differently spelled listing URL (LIVE-01).
        listing = strip_tracking(await destination_validator(str(plan.product_url)))
        seller = urlsplit(listing).hostname.lower().removeprefix("www.")
        urls = [listing]
        for record in records[:5]:
            url = strip_tracking(public_url(record.source_url))
            if urlsplit(url).hostname.lower().removeprefix("www.") == seller and url not in urls:
                urls.append(await destination_validator(url))
            if len(urls) == 3:
                break
        if not hasattr(provider, "extract_sources"):
            return PromiseSourceResult([], "unavailable", len(urls))
        async with asyncio.timeout(15):
            extracted = await provider.extract_sources(urls)
        return PromiseSourceResult(extracted, "partial" if extracted else "empty", len(urls))
    except TimeoutError:
        return PromiseSourceResult([], "timeout", len(urls))
    except UnsafeURL:
        return PromiseSourceResult([], "unsafe_url", len(urls))
    except ResearchUnavailable as exc:
        return PromiseSourceResult([], exc.reason, len(urls))
