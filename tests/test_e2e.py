"""Injected offline workflow QA; no external Grok/search/SMS calls."""
import asyncio
from app.config import Settings
from app.models import ShoppingRequest, OrchestratorPlan, Assessment
from app.workflow.service import Contracts, EvaluationWorkflow
from app.decision import decide, format_sms


def test_injected_source_free_workflow():
    async def extract(request):
        return OrchestratorPlan(request_id=request.request_id,intent='evaluate_purchase',product_url='https://shop.example/perfume',tasks=[dict(kind='verify_seller',query='shop.example')],data_mode='mock')
    async def research(plan, task):
        return []
    workflow = EvaluationWorkflow(Contracts(ShoppingRequest,OrchestratorPlan,Assessment),extract,research,decide,Settings())
    result = asyncio.run(workflow.evaluate(ShoppingRequest(request_id='qa',message_text='https://shop.example/perfume')))
    assert result.decision == 'VERIFY_FIRST'
    assert result.evidence == []
    assert '[SYNTHETIC/MOCK]' in format_sms(result)
