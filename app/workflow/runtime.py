"""Application composition only; B/C/D retain extraction, research and policy."""
from contextlib import asynccontextmanager

import httpx

from app.decision import decide
from app.models import Assessment, OrchestratorPlan, ShoppingRequest
from app.research.evidence import SellerResearch
from app.research.url_safety import validate_public_destination
from app.services.grok import GrokExtractor, XAICompletionClient
from app.services.tavily import TavilyProvider
from app.workflow.service import Contracts, EvaluationWorkflow


@asynccontextmanager
async def runtime_workflow(settings, *, xai_transport=None, tavily_transport=None,
                           destination_validator=validate_public_destination):
    # No requests on startup; live requests require explicit mode and an evaluation.
    async with httpx.AsyncClient(transport=xai_transport, timeout=settings.grok_timeout_seconds,
                                follow_redirects=False, trust_env=False) as client:
        live = settings.provider_mode == "live"
        completion = (XAICompletionClient(client, api_key=settings.xai_api_key,
                                         model=settings.xai_model)
                      if live and settings.xai_api_key and settings.xai_model else None)
        extractor = GrokExtractor(completion, timeout_seconds=settings.grok_timeout_seconds)
        research = SellerResearch(TavilyProvider(
            settings.tavily_api_key if live else None, transport=tavily_transport),
            destination_validator=destination_validator)

        async def research_with_status(plan, task):
            # Missing key/offline must not even perform seller DNS resolution.
            if not live or not settings.tavily_api_key:
                from app.research.evidence import ResearchResult
                return ResearchResult([], "unavailable")
            return await research.research_with_status(plan, task)

        def decision(request, plan, evidence):
            assessment = decide(request, plan, evidence)
            if plan.requires_user_input and plan.clarification:
                updates = {"summary": plan.clarification}
                if plan.status in {"unavailable", "timeout", "invalid_output"}:
                    # Do not ask for a URL the user already supplied when the
                    # actual gap is provider availability or extraction failure.
                    updates["missing_information"] = [plan.clarification]
                assessment = assessment.model_copy(update=updates)
            return assessment

        yield EvaluationWorkflow(Contracts(ShoppingRequest, OrchestratorPlan, Assessment),
                                 extractor.extract, research_with_status, decision, settings)
