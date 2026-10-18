"""Cross-channel contract checks between the Python backend and the extension client.

tests/qa_fixtures/cross_channel_response.json is a SYNTHETIC backend response produced
by the mocked pipeline below. extension/test/qa-cross-channel.test.js feeds the same
file through the extension's validator and view-model, so the two channels are
checked against one assessment (OUT-03). This test keeps the fixture in sync
with the backend. tests/qa_fixtures/extension_message_texts.json holds the exact
message_text strings that extension/src/lib/request.js builds (checked on the node side)."""
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from app.decision import format_sms
from app.models import Assessment
from app.services.grok import _provided_urls
from tests.test_qa_acceptance import (CONFLICT_EXTRACT, CONFLICT_ROW, CONFLICT_SEARCH, TOKEN, Harness)

QA = Path(__file__).parent / "qa_fixtures"
CROSS = QA / "cross_channel_response.json"
MESSAGES = QA / "extension_message_texts.json"
VOLATILE = re.compile(r'"(retrieved_at|registered_at)": "[^"]*"')


def produce():
    harness = Harness(search=CONFLICT_SEARCH + [
        {"url": "https://synthetic-shop.com/faq", "title": "FAQ", "content": "synthetic-shop.com shipping FAQ"}],
        extract=CONFLICT_EXTRACT, promise={"records": [CONFLICT_ROW]})
    response = harness.post(path="/api/v1/extension/evaluate", headers={"Authorization": f"Bearer {TOKEN}"},
                            request_id="qa-cross-channel")
    assert response.status_code == 200
    return response.json()


def stable(value):
    return VOLATILE.sub(r'"\1": "<time>"', json.dumps(value, sort_keys=True))


def test_OUT_03_cross_channel_fixture_matches_current_backend_output():
    stored = json.loads(CROSS.read_text())
    assert stored["label"].startswith("SYNTHETIC")
    assert stable(stored["response"]) == stable(produce())
    assessment = Assessment.model_validate(stored["response"]["assessment"])
    assert format_sms(assessment) == stored["response"]["message_text"]


def _cases():
    data = json.loads(MESSAGES.read_text())
    assert data["label"].startswith("SYNTHETIC")
    return data["cases"]


@pytest.mark.parametrize("case", [c for c in _cases() if not c.get("known_defect")], ids=lambda c: c["id"])
def test_INPUT_01_backend_extracts_exact_listing_url_and_price_from_extension_message(case):
    assert _provided_urls(case["message_text"]) == {case["href"]}
    if case["price"]:
        amounts = {Decimal(v.replace(",", "")) for v in re.findall(
            r"(?:\$|USD\s*)(\d+(?:,\d{3})*(?:\.\d{1,2})?)(?![\d.])", case["message_text"], flags=re.IGNORECASE)}
        assert amounts == {Decimal(case["price"].lstrip("$"))}


@pytest.mark.xfail(strict=True, reason="QA-03: backend URL regex truncates valid listing hrefs containing ' or ending in ) or .")
@pytest.mark.parametrize("case", [c for c in _cases() if c.get("known_defect")], ids=lambda c: c["id"])
def test_INPUT_01_backend_extracts_exact_listing_url_with_punctuation(case):
    assert _provided_urls(case["message_text"]) == {case["href"]}
