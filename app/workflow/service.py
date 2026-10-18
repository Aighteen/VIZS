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
            if plan.intent == "evaluate_purchase" and not plan.requires_user_input:
                # P0 seller research only. Model output cannot expand tool permissions.
                tasks = [t for t in plan.tasks if t.kind == "verify_seller"]
                for task in tasks[:self.settings.max_research_calls]:
                    evidence.extend(await self.research(plan, task))
            result = self.contracts.assessment.model_validate(
                self.decide(request, plan, evidence))
            if result.request_id != request.request_id:
                raise ValueError("Mismatched assessment correlation")
            return result
