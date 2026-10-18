"""Backend-owned sequencing; contracts and domain behavior belong to B/C/D."""
import asyncio
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
                 settings: Settings):
        self.contracts = contracts
        self.extract = extract
        self.research = research
        self.decide = decide
        self.settings = settings

    async def evaluate(self, request: BaseModel) -> BaseModel:
        async with asyncio.timeout(self.settings.evaluation_timeout_seconds):
            request = self.contracts.request.model_validate(request.model_dump())
            plan = self.contracts.plan.model_validate(await self.extract(request))
            if plan.request_id != request.request_id:
                raise ValueError("Mismatched plan correlation")
            evidence = []
            research_gaps = []
            research_reports = []
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
                        gap = {"unavailable": "Seller research is unavailable; try again later.",
                               "unsafe_url": "Listing destination was unsafe or could not be resolved.",
                               "empty": "No relevant seller sources were returned.",
                               "filtered": "Returned sources did not match the seller or failed validation.",
                               "timeout": "Seller research timed out; try again later.",
                               "partial": findings.uncertainty}.get(findings.status)
                        if gap and gap not in research_gaps:
                            research_gaps.append(gap)
            result = self.contracts.assessment.model_validate(
                self.decide(request, plan, evidence))
            if result.request_id != request.request_id:
                raise ValueError("Mismatched assessment correlation")
            if research_reports and hasattr(result, "research"):
                result = self.contracts.assessment.model_validate(result.model_copy(update={
                    "research": research_reports}).model_dump())
            if research_gaps and hasattr(result, "missing_information"):
                result = self.contracts.assessment.model_validate(result.model_copy(update={
                    "missing_information": (research_gaps + result.missing_information)[:10]}).model_dump())
            return result
