import json
from pathlib import Path
import pytest
from app.models import Evidence, OrchestratorPlan, ShoppingRequest
from app.decision import decide

@pytest.fixture
def request_data():
    return ShoppingRequest(request_id='x',message_text='https://shop.example/perfume')

@pytest.fixture
def plan():
    return OrchestratorPlan(request_id='x',intent='evaluate_purchase',product_url='https://shop.example/perfume',data_mode='mock')

@pytest.fixture
def official():
    return Evidence.model_validate(json.loads(Path('tests/fixtures/positive.json').read_text())['evidence'][0])

def test_official(request_data, plan, official):
    result = decide(request_data,plan,[official])
    assert result.seller_risk == 'LOWER_RISK'
    assert result.evidence == [official]

@pytest.mark.parametrize('change', [dict(finding='discount'),dict(finding='authorization_unknown'),dict(claim_status='allegation'),dict(evidence_type='unverified_review'),dict(seller_domain='different.example'),dict(excerpt=None)])
def test_weak_is_not_authorization(request_data,plan,official,change):
    assert decide(request_data,plan,[official.model_copy(update=change)]).decision == 'VERIFY_FIRST'

def test_missing_and_empty(request_data,plan):
    assert decide(request_data,plan,[]).decision == 'VERIFY_FIRST'
    assert decide(request_data,plan.model_copy(update={'product_url':None}),[]).decision == 'NEED_MORE_INFORMATION'

def test_independent_adverse_and_conflict(request_data,plan,official):
    one = Evidence.model_validate({**official.model_dump(), 'finding':'substantial_adverse','evidence_type':'regulatory','source_url':'https://regulator.example/action'})
    two = Evidence.model_validate({**one.model_dump(), 'source_url':'https://investigator.example/report','evidence_type':'investigation'})
    one = Evidence.model_validate(one.model_dump())
    assert decide(request_data,plan,[one,one]).decision == 'VERIFY_FIRST'
    assert decide(request_data,plan,[one,two]).decision == 'AVOID'
    assert decide(request_data,plan,[one,two,official]).decision == 'VERIFY_FIRST'
    assert decide(request_data,plan,[official.model_copy(update={'polarity':'contradicts'})]).decision == 'VERIFY_FIRST'

def test_mismatched_identity(request_data,plan):
    with pytest.raises(ValueError):
        decide(request_data,plan.model_copy(update={'request_id':'other'}),[])



def test_unverified_relevant_sources_survive_without_changing_decision(request_data,plan,official):
    weak=official.model_copy(update={"claim_status":"unknown","evidence_type":"search_snippet","finding":"other","polarity":"neutral"})
    unrelated=weak.model_copy(update={"seller_domain":"other.example"})
    result=decide(request_data,plan,[weak,unrelated])
    assert result.decision=="VERIFY_FIRST"
    assert result.evidence==[weak]
    assert result.evidence[0].claim_status=="unknown"
