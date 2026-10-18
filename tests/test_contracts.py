import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.models import Assessment, Evidence, OrchestratorPlan, ShoppingRequest

@pytest.mark.parametrize('name', ['positive', 'insufficient'])
def test_labeled_fixtures(name):
    item = Assessment.model_validate_json(Path(f'tests/fixtures/{name}.json').read_text())
    assert item.data_mode == 'mock'

def test_bounded_extra_forbidden():
    with pytest.raises(ValidationError):
        ShoppingRequest(request_id='x', message_text='hello', secret='no')
    with pytest.raises(ValidationError):
        OrchestratorPlan(request_id='x', intent='evaluate_purchase', tasks=[{'kind':'arbitrary_api','query':'x'}])

def test_money_and_aware_time():
    plan = OrchestratorPlan(request_id='x',intent='evaluate_purchase',purchase_price='12.50')
    assert str(plan.purchase_price) == '12.50'
    evidence = json.loads(Path('tests/fixtures/positive.json').read_text())['evidence'][0]
    evidence['retrieved_at'] = '2026-10-17T12:00:00'
    with pytest.raises(ValidationError):
        Evidence.model_validate(evidence)

def test_risk_and_mock_consistency():
    data = json.loads(Path('tests/fixtures/positive.json').read_text())
    data['decision'] = 'AVOID'
    with pytest.raises(ValidationError):
        Assessment.model_validate(data)
    data['decision'] = 'CONSIDER_BUYING'
    data['data_mode'] = 'live'
    with pytest.raises(ValidationError):
        Assessment.model_validate(data)


def test_research_report_count_and_status_consistency():
    from app.models import ResearchReport
    valid=ResearchReport(status="partial",provider_called=True,records_received=3,records_retained=1,records_filtered=2)
    assert valid.records_retained==1
    for fields in [dict(status="partial"),dict(status="filtered"),dict(status="empty",provider_called=True,records_received=1,records_retained=1),dict(status="partial",records_received=1,records_retained=1),dict(status="partial",provider_called=True,records_received=2,records_retained=1)]:
        with pytest.raises(ValidationError):
            ResearchReport(**fields)
