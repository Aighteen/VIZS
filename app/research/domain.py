"""Registration context from a fixed registry endpoint; never follows RDAP links.

Verified docs: https://www.verisign.com/news-insights/registration-data-access-protocol/help/
Only exact second-level .com/.net names are supported; no public-suffix guessing.
"""
import asyncio
import json
from datetime import datetime, timezone

import httpx
from app.models import PromiseContext
from app.research.url_safety import public_url, UnsafeURL
from urllib.parse import urlsplit


class DomainLookup:
    def __init__(self, *, transport=None, timeout=5):
        if not 0 < timeout <= 10:
            raise ValueError("Invalid domain lookup timeout")
        self.transport, self.timeout = transport, timeout

    async def lookup(self, domain):
        unavailable = PromiseContext(status="unavailable", explanation="Registration lookup unavailable; no inference about seller credibility.")
        try:
            normalized = public_url("https://" + domain)
            parsed = urlsplit(normalized)
            if parsed.path != "/" or parsed.query or parsed.port:
                return unavailable
            host = parsed.hostname.removeprefix("www.")
            labels = host.split(".")
            if len(labels) != 2 or labels[-1] not in {"com", "net"}:
                return unavailable
            endpoint = f"https://rdap.verisign.com/{labels[-1]}/v1/domain/{host}"
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(transport=self.transport, timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
                    async with client.stream("GET", endpoint, headers={"Accept": "application/rdap+json"}) as response:
                        if response.status_code != 200:
                            return unavailable
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(content) + len(chunk) > 64000:
                                return unavailable
                            content.extend(chunk)
                        payload = json.loads(content)
            if not isinstance(payload, dict) or payload.get("ldhName", "").lower() != host:
                return unavailable
            dates = [datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00")) for event in payload.get("events", []) if event.get("eventAction") == "registration"]
            now = datetime.now(timezone.utc)
            if len(dates) != 1 or dates[0].tzinfo is None or dates[0] > now:
                return unavailable
            return PromiseContext(status="context_only", registered_at=dates[0], source_url=endpoint, retrieved_at=now, explanation="Registry registration date is domain context, not business age, authenticity or fraud evidence.")
        except (UnsafeURL, ValueError, TypeError, KeyError, AttributeError, httpx.HTTPError, TimeoutError):
            return unavailable
