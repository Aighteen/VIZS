import asyncio

import pytest

from app.config import Settings
from app.workflow.jobs import CapacityExceeded, Jobs


def test_concurrent_duplicates_capacity_and_failure_without_retry():
    async def scenario():
        jobs = Jobs(Settings(max_jobs=1, dedupe_capacity=2))
        release = asyncio.Event()
        calls = []

        async def run():
            calls.append(1)
            await release.wait()
            raise RuntimeError("ambiguous outbound failure")

        results = await asyncio.gather(*(jobs.submit("same", run) for _ in range(30)))
        assert sum(results) == 1
        with pytest.raises(CapacityExceeded):
            await jobs.submit("other", run)
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert calls == [1]
        assert jobs.status["same"] == "failed"
        assert not await jobs.submit("same", run)

    asyncio.run(scenario())


def test_job_timeout_and_expiry():
    async def scenario():
        clock = [0.0]
        jobs = Jobs(Settings(evaluation_timeout_seconds=0.01, dedupe_ttl_seconds=1,
                             dedupe_capacity=1), clock=lambda: clock[0])

        async def slow():
            await asyncio.sleep(1)

        assert await jobs.submit("first", slow)
        await asyncio.gather(*list(jobs.tasks))
        assert jobs.status["first"] == "failed"
        assert not jobs.active
        clock[0] = 2.0
        assert await jobs.submit("second", slow)
        await asyncio.gather(*list(jobs.tasks))
        assert jobs.status["second"] == "failed"

    asyncio.run(scenario())
