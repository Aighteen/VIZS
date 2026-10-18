"""Bounded single-process prototype, neither durable nor multi-worker safe."""
import asyncio
from collections import OrderedDict
from time import monotonic

from app.config import Settings


class CapacityExceeded(Exception):
    pass


class Jobs:
    def __init__(self, settings: Settings, clock=monotonic):
        self.settings = settings
        self.clock = clock
        self.seen = OrderedDict()
        self.active = set()
        self.status = OrderedDict()
        self.lock = asyncio.Lock()
        self.tasks = set()

    async def submit(self, key, run):
        async with self.lock:
            now = self.clock()
            for old, expires in list(self.seen.items()):
                if expires <= now and old not in self.active:
                    del self.seen[old]
                    self.status.pop(old, None)
            if key in self.seen:
                return False
            if len(self.active) >= self.settings.max_jobs or len(self.seen) >= self.settings.dedupe_capacity:
                raise CapacityExceeded
            self.seen[key] = now + self.settings.dedupe_ttl_seconds
            self.active.add(key)
            self.status[key] = "queued"
            task = asyncio.create_task(self._run(key, run))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return True

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, key, run):
        try:
            self.status[key] = "running"
            async with asyncio.timeout(self.settings.evaluation_timeout_seconds):
                await run()
            self.status[key] = "sent"
        except asyncio.CancelledError:
            self.status[key] = "cancelled"
            raise
        except Exception:
            # Do not log payloads, destinations, or exception text. No ambiguous-send retry.
            self.status[key] = "failed"
        finally:
            self.active.discard(key)
