"""Backend-owned sequencing; contracts and domain behavior belong to B/C/D."""
import asyncio
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from pydantic import BaseModel

from app.config import Settings


class WorkflowUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Contracts:
    request: type[BaseModel]
    plan: type[BaseModel]
    assessment: type[BaseModel]


class EvaluationWorkflow:
    def __init__(self, contracts: Contracts, extract: Callable[..., Awaitable],
                 research: Callable[..., Awaitable], decide: Callable[..., BaseModel],
                 settings: Settings, *, promise_resolver: Callable[..., Awaitable] | None = None,
                 brand_research: Callable[..., Awaitable] | None = None):
        self.contracts = contracts
        self.extract = extract
        self.research = research
        self.decide = decide
        self.settings = settings
        self.promise_resolver = promise_resolver
        self.brand_research = brand_research
        self._completed: dict[str, tuple[float, BaseModel]] = {}

    async def evaluate(self, request: BaseModel) -> BaseModel:
        request = self.contracts.request.model_validate(request.model_dump())
        now = time.monotonic()
        self._completed = {
            key: value for key, value in self._completed.items()
            if value[0] > now
        }
        cache_key = request.model_dump_json()
        cached = self._completed.get(cache_key)
        if cached is not None:
            return self.contracts.assessment.model_validate(cached[1].model_dump())
        async with asyncio.timeout(self.settings.evaluation_timeout_seconds):
            plan = self.contracts.plan.model_validate(await self.extract(request))
            if plan.request_id != request.request_id:
                raise ValueError("Mismatched plan correlation")
            evidence = []
            research_gaps = []
            research_reports = []
            source_records = []
            if plan.intent == "evaluate_purchase" and not plan.requires_user_input:
                # P0 seller research only. Model output cannot expand tool permissions.
                tasks = [t for t in plan.tasks if t.kind == "verify_seller"]
                for task in tasks[:self.settings.max_research_calls]:
                    findings = await self.research(plan, task)
                    if isinstance(findings, list):
                        evidence.extend(findings)
                    else:
                        evidence.extend(findings.evidence)
                        research_reports.append(findings.report())
                        source_records.extend(getattr(findings, "source_records", []))
                        gap = {"unavailable": "Seller research is unavailable; try again later.",
                               "unsafe_url": "Listing destination was unsafe or could not be resolved.",
                               "empty": "No relevant seller sources were returned.",
                               "filtered": "Returned sources did not match the seller or failed validation.",
                               "timeout": "Seller research timed out; try again later.",
                               "partial": findings.uncertainty}.get(findings.status)
                        if gap and gap not in research_gaps:
                            research_gaps.append(gap)
                if (self.brand_research is not None
                        and all(report.status != "unsafe_url" for report in research_reports)):
                    # One fixed brand-direct query; its snippets are re-checked by policy.
                    found = await self.brand_research(plan)
                    # Its records only ever add the brand-direct outcome; seller research
                    # reports and gaps stay those of the seller tasks.
                    evidence.extend(found.evidence)
            sheet = None
            if self.promise_resolver and plan.intent == "evaluate_purchase" and not plan.requires_user_input and plan.product_url:
                sheet = await self.promise_resolver(plan, source_records[:8])
            result = self.contracts.assessment.model_validate(
                self.decide(request, plan, evidence, promise_sheet=sheet) if self.promise_resolver
                else self.decide(request, plan, evidence))
            if result.request_id != request.request_id:
                raise ValueError("Mismatched assessment correlation")
            if research_reports and hasattr(result, "research"):
                result = self.contracts.assessment.model_validate(result.model_copy(update={
                    "research": research_reports}).model_dump())
            if research_gaps and hasattr(result, "missing_information"):
                result = self.contracts.assessment.model_validate(result.model_copy(update={
                    "missing_information": (research_gaps + result.missing_information)[:10]}).model_dump())
            if len(self._completed) >= self.settings.dedupe_capacity:
                oldest = min(self._completed, key=lambda key: self._completed[key][0])
                del self._completed[oldest]
            self._completed[cache_key] = (time.monotonic() + self.settings.dedupe_ttl_seconds, result)
            return result
