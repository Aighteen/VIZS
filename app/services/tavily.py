"""Bounded Tavily Search adapter, verified against official Search API docs.

https://docs.tavily.com/documentation/api-reference/endpoint/search
No retries, redirects, raw page fetches, or generated-answer consumption.
"""
import asyncio
import json
from datetime import datetime, timezone

import httpx

from app.research.provider import ResearchUnavailable, SearchResponse, SourceRecord
from app.research.url_safety import UnsafeURL, public_url, same_page_key


def _canonical_answer(returned, by_page, returned_url):
    """A provider may answer a ``?variant=`` listing under the product's canonical URL
    (Shopify). Same host and identical path, with content parameters only dropped
    (never added or changed), for exactly one requested URL. The record then keeps
    the provider's canonical URL, because that is the page the text came from."""
    candidates = by_page.get(returned[:2], [])
    if len(candidates) != 1 or not set(returned[2]) < set(candidates[0][2]):
        return None
    return public_url(returned_url).split("#", 1)[0]


class TavilyProvider:
    def __init__(self, api_key: str | None, *, transport=None, timeout: float = 8, max_results: int = 5,
                 extract_timeout: float | None = None):
        extract_timeout = timeout if extract_timeout is None else extract_timeout
        if not 0 < timeout <= 15 or not 0 < extract_timeout <= 15 or not 1 <= max_results <= 5:
            raise ValueError("Research limits out of range")
        self.api_key = api_key
        self.transport = transport
        self.timeout = timeout
        # Extract fetches whole pages and is slower than Search.
        self.extract_timeout = extract_timeout
        self.max_results = max_results

    async def search(self, query: str) -> list[SourceRecord]:
        return (await self.search_with_status(query)).records

    async def search_with_status(self, query: str) -> SearchResponse:
        if not self.api_key:
            raise ResearchUnavailable("Research provider not configured")
        if not isinstance(query, str) or not query.strip() or len(query) > 400:
            raise ResearchUnavailable("Invalid research query")
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
                    async with client.stream("POST", "https://api.tavily.com/search", headers={"Authorization": f"Bearer {self.api_key}"}, json={"query": query, "search_depth": "basic", "max_results": self.max_results, "include_answer": False, "include_raw_content": False, "include_images": False, "auto_parameters": False}) as response:
                        if response.status_code != 200:
                            raise ResearchUnavailable("Research provider rejected request")
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(chunks) + len(chunk) > 128_000:
                                raise ResearchUnavailable("Research response too large")
                            chunks.extend(chunk)
                        payload = json.loads(chunks)
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ResearchUnavailable("Research provider timed out", reason="timeout") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ResearchUnavailable("Research provider unavailable or malformed") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ResearchUnavailable("Research provider returned invalid records")
        records = []
        seen = set()
        now = datetime.now(timezone.utc)
        for item in payload["results"][:self.max_results]:
            if not isinstance(item, dict) or not isinstance(item.get("content"), str):
                continue
            try:
                url = public_url(item.get("url"))
            except UnsafeURL:
                continue
            excerpt = item["content"].strip()[:2000]
            if not excerpt or url in seen:
                continue
            seen.add(url)
            title = item.get("title")
            records.append(SourceRecord(url, title[:200] if isinstance(title, str) else "", excerpt, now))
        return SearchResponse(records, min(len(payload["results"]), self.max_results))

    async def extract_sources(self, urls: list[str], *, markdown: bool = False, max_chars: int = 60000,
                              content_kind: str = "merchant_page") -> list[SourceRecord]:
        """One fixed-provider Extract call; never connect to merchant URLs.

        Contract: https://docs.tavily.com/documentation/api-reference/endpoint/extract
        The returned content is merchant wording, not proof of fulfillment.
        """
        if not self.api_key:
            raise ResearchUnavailable("Research provider not configured")
        if not 1 <= len(urls) <= 3:
            raise ResearchUnavailable("Extraction URL limit exceeded")
        try:
            admitted = list(dict.fromkeys(public_url(url) for url in urls))
        except UnsafeURL as exc:
            raise ResearchUnavailable("Unsafe extraction URL") from exc
        try:
            async with asyncio.timeout(self.extract_timeout):
                async with httpx.AsyncClient(transport=self.transport, timeout=self.extract_timeout, follow_redirects=False, trust_env=False) as client:
                    async with client.stream("POST", "https://api.tavily.com/extract", headers={"Authorization": f"Bearer {self.api_key}"}, json={"urls": admitted, "extract_depth": "basic", "format": "markdown" if markdown else "text", "include_images": False}) as response:
                        if response.status_code != 200:
                            raise ResearchUnavailable("Policy extraction unavailable")
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(chunks) + len(chunk) > 256_000:
                                raise ResearchUnavailable("Policy response too large")
                            chunks.extend(chunk)
                        payload = json.loads(chunks)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ValueError("Malformed policy results")
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ResearchUnavailable("Policy extraction timed out", reason="timeout") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ResearchUnavailable("Policy extraction unavailable") from exc
        records = []
        seen = set()
        # The provider may respell a requested URL (scheme, www., trailing slash,
        # encoding, tracking parameters). Same host+path+content query is the same
        # page; the record keeps the URL we admitted, never the provider's spelling.
        requested = {}
        by_page = {}
        for url in admitted:
            key = same_page_key(url)
            requested.setdefault(key, url)
            by_page.setdefault(key[:2], []).append(key)
        for item in payload["results"][:3]:
            if not isinstance(item, dict) or not isinstance(item.get("raw_content"), str):
                continue
            try:
                returned = same_page_key(item.get("url"))
                url = requested.get(returned)
                if url is None:
                    url = _canonical_answer(returned, by_page, item.get("url"))
            except UnsafeURL:
                continue
            # Reject substituted/redirect destinations. Provider may return partial success.
            if url is None or url in seen or not item["raw_content"].strip():
                continue
            seen.add(url)
            title = "Retrieved merchant page" if content_kind == "merchant_page" else "Retrieved reference page"
            records.append(SourceRecord(url, title, item["raw_content"][:min(max_chars, 60000)],
                                        datetime.now(timezone.utc), content_kind=content_kind))
        return records
