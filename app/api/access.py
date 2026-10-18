"""Local extension pairing and process-local request budget; no public auth claim."""
import asyncio
import secrets
from collections import deque
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import HTTPException


class ExtensionAccess:
    def __init__(self, settings, *, clock=monotonic):
        self.settings = settings
        self.clock = clock
        self.starts = deque()
        self.active = 0
        self.lock = asyncio.Lock()

    def authenticate(self, headers):
        expected = self.settings.extension_token
        if not expected:
            raise HTTPException(503, "Extension pairing is not configured")
        supplied = headers.get("authorization", "")
        if len(supplied) > 512 or not supplied.startswith("Bearer ") or not secrets.compare_digest(supplied[7:].encode(), expected.encode()):
            raise HTTPException(401, "Invalid extension pairing", headers={"WWW-Authenticate": "Bearer"})
        origin = headers.get("origin")
        # Origin is not identity; some extension fetches omit it. Pairing always required.
        if origin and origin not in self.settings.extension_origins:
            raise HTTPException(403, "Extension origin is not allowed")

    @asynccontextmanager
    async def permit(self):
        async with self.lock:
            now = self.clock()
            while self.starts and now - self.starts[0] >= 60:
                self.starts.popleft()
            if len(self.starts) >= self.settings.extension_requests_per_minute or self.active >= self.settings.extension_max_inflight:
                raise HTTPException(429, "Extension request budget exceeded", headers={"Retry-After": "60"})
            self.starts.append(now)
            self.active += 1
        try:
            yield
        finally:
            async with self.lock:
                self.active -= 1
