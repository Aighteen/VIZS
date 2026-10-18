"""Application composition only; B/C/D retain extraction, research and policy."""
from contextlib import asynccontextmanager
import asyncio
import contextvars
import time
from urllib.parse import urlsplit

import httpx

from app.decision import decide
from app.models import Assessment, OrchestratorPlan, ShoppingRequest
from app.research.evidence import SellerResearch
from app.research.url_safety import validate_public_destination
from app.services.grok import GrokExtractor, XAICompletionClient
from app.services.tavily import TavilyProvider
from app.research.domain import DomainLookup
from app.research.promises import collect_promise_sources
from app.research.promise_extractor import PromiseExtractor, XAIPromiseCompletionClient, reader_timeout
from app.workflow.service import Contracts, EvaluationWorkflow


@asynccontextmanager
async def runtime_workflow(settings, *, xai_transport=None, tavily_transport=None,
                           destination_validator=validate_public_destination, domain_transport=None):
    # No requests on startup; live requests require explicit mode and an evaluation.
    async with httpx.AsyncClient(transport=xai_transport, timeout=settings.grok_timeout_seconds,
                                follow_redirects=False, trust_env=False) as client:
        live = settings.provider_mode == "live"
        completion = (XAICompletionClient(client, api_key=settings.xai_api_key,
                                         model=settings.xai_model)
                      if live and settings.xai_api_key and settings.xai_model else None)
        extractor = GrokExtractor(completion, timeout_seconds=settings.grok_timeout_seconds)
        # Extract stays under collect_promise_sources' 15 s bound.
        provider = TavilyProvider(settings.tavily_api_key if live else None, transport=tavily_transport,
                                  extract_timeout=14)
        research = SellerResearch(provider, destination_validator=destination_validator)
        # Per-evaluation start, so the promise reader gets the remaining budget.
        started = contextvars.ContextVar("evaluation_started", default=None)

        async def timed_extract(request):
            started.set(time.monotonic())
            return await extractor.extract(request)

        async def resolve_promises(plan, records):
            # Offline/missing research configuration must not cause extraction or registry requests.
            if not live or not settings.tavily_api_key:
                return await PromiseExtractor().extract(plan, [])
            collected = await collect_promise_sources(provider, plan, records=records,
                                                       destination_validator=destination_validator)
            policy_records = collected.records + records
            usable_page = any(record.content_kind == "merchant_page" for record in collected.records)
            start = started.get()
            promise_timeout = reader_timeout(settings, None if start is None else time.monotonic() - start)
            # Dedicated request bound: the shared client's read timeout is the plan's.
            promise_client = (XAIPromiseCompletionClient(client, api_key=settings.xai_api_key, model=settings.promise_model,
                                                         request_timeout=promise_timeout)
                              if completion is not None and usable_page else None)
            promise_extractor = PromiseExtractor(promise_client, timeout_seconds=promise_timeout)
            # Independent context lookup never expands its fixed .com/.net registry allowlist.
            sheet, domain = await asyncio.gather(
                promise_extractor.extract(plan, policy_records, collection=collected),
                DomainLookup(transport=domain_transport).lookup(urlsplit(str(plan.product_url)).hostname))
            return sheet.model_copy(update={"domain_context": domain})

        async def research_with_status(plan, task):
            # Missing key/offline must not even perform seller DNS resolution.
            if not live or not settings.tavily_api_key:
                from app.research.evidence import ResearchResult
                return ResearchResult([], "unavailable")
            return await research.research_with_status(plan, task)

        async def brand_research(plan):
            if not live or not settings.tavily_api_key:
                from app.research.evidence import ResearchResult
                return ResearchResult([], "skipped")
            return await research.brand_direct_with_status(plan)

        def decision(request, plan, evidence, promise_sheet=None):
            assessment = decide(request, plan, evidence, promise_sheet=promise_sheet)
            if plan.requires_user_input and plan.clarification:
                updates = {"summary": plan.clarification}
                if plan.status in {"unavailable", "timeout", "invalid_output"}:
                    # Do not ask for a URL the user already supplied when the
                    # actual gap is provider availability or extraction failure.
                    updates["missing_information"] = [plan.clarification]
                assessment = assessment.model_copy(update=updates)
            return assessment

        yield EvaluationWorkflow(Contracts(ShoppingRequest, OrchestratorPlan, Assessment),
                                 timed_extract, research_with_status, decision, settings,
                                 promise_resolver=resolve_promises, brand_research=brand_research)
