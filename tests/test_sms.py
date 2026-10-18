import json
from pathlib import Path
import pytest
from app.models import Assessment
from app.decision import format_sms

@pytest.mark.parametrize('name', ['positive', 'insufficient'])
def test_labels_uncertainty_and_bounds(name):
    assessment = Assessment.model_validate_json(Path(f'tests/fixtures/{name}.json').read_text())
    text = format_sms(assessment)
    assert text.startswith('[SYNTHETIC/MOCK]')
    assert assessment.seller_risk.value in text
    assert 'authenticity is not established' in text
    assert len(text) <= 1000
    for evidence in assessment.evidence:
        assert str(evidence.source_url) in text

def test_long_source_never_truncated():
    data = json.loads(Path('tests/fixtures/positive.json').read_text())
    data['evidence'][0]['source_url'] = 'https://brand.example/' + 'a' * 1000
    text = format_sms(Assessment.model_validate(data),350)
    assert len(text) <= 350
    assert 'Source:' not in text
    assert 'Source links exceed message length' in text

def test_unsafe_budget_rejected():
    data = Assessment.model_validate_json(Path('tests/fixtures/insufficient.json').read_text())
    with pytest.raises(ValueError):
        format_sms(data,30)


def test_unverified_links_are_intact_deduplicated_and_not_endorsements():
    data=json.loads(Path('tests/fixtures/positive.json').read_text(encoding='utf-8'))
    data.update(seller_risk="INSUFFICIENT_EVIDENCE",decision="VERIFY_FIRST")
    item=data['evidence'][0]
    item.update(claim_status="unknown",evidence_type="search_snippet",finding="other",polarity="neutral")
    data['evidence']=[item,item]
    text=format_sms(Assessment.model_validate(data))
    assert "Seller authorization unconfirmed" in text
    assert "Unverified source:" in text
    assert text.count(item['source_url'])==1
    assert "authenticity is not established" in text
    assert len(text)<=1000


def test_promise_conflict_phone_output_retains_both_quotes_and_links():
    from app.models import PromiseSheet
    from app.decision import validate_promise_sheet
    assessment = Assessment.model_validate_json(Path("tests/fixtures/insufficient.json").read_text())
    sheet = PromiseSheet.model_validate_json(Path("tests/fixtures/promise_conflict.json").read_text())
    assessment.promise_sheet = validate_promise_sheet(sheet, sheet.sources)
    text = format_sms(assessment)
    assert "Potentially differing terms; compare conditions" in text
    assert '"Free returns."' in text
    assert '"US customers pay return shipping."' in text
    assert "https://shop.example/returns" in text
    assert "Fulfillment unverified" in text
    assert "authenticity is not established" in text
    assert len(text) <= 1000


def test_promise_unknown_and_unavailable_phone_wording():
    from app.models import PromiseSheet
    assessment = Assessment.model_validate_json(Path("tests/fixtures/insufficient.json").read_text())
    for name, wording in [("missing", "not disclosed in inspected source"), ("unavailable", "check unavailable")]:
        assessment.promise_sheet = PromiseSheet.model_validate_json(Path(f"tests/fixtures/promise_{name}.json").read_text())
        assert wording in format_sms(assessment)
