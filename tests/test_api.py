"""Test-only stand-ins, NOT D's finalized domain contracts or real research."""
import asyncio
from typing import Literal

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.config import Settings
from app.main import create_app
from app.workflow.service import Contracts, EvaluationWorkflow


class FakeRequest(BaseModel):
    request_id: str
    message_text: str = Field(min_length=1, max_length=4000)
    channel: Literal["debug", "sms"] = "debug"


class FakeTask(BaseModel):
    kind: str


class FakePlan(BaseModel):
    request_id: str
    intent: str = "evaluate_purchase"
    requires_user_input: bool = False
    tasks: list[FakeTask] = Field(default_factory=list)


class FakeAssessment(BaseModel):
    request_id: str
    data_mode: Literal["mock"] = "mock"
    summary: str = "Synthetic test only; no seller research performed."


def fake_workflow(settings=None, extract=None, research=None):
    async def default_extract(request):
        return FakePlan(request_id=request.request_id)

    async def default_research(plan, task):
        return []

    return EvaluationWorkflow(
        Contracts(FakeRequest, FakePlan, FakeAssessment), extract or default_extract,
        research or default_research,
        lambda request, plan, evidence: FakeAssessment(request_id=request.request_id),
        settings or Settings())


def test_health_and_unwired_evaluation():
    with TestClient(create_app()) as client:
        assert client.get("/healthz").json() == {
            "status": "ok", "evaluation_ready": False, "photon_enabled": False}
        assert client.post("/api/v1/evaluate", json={}).status_code == 503
        assert client.post("/api/v1/mock/messages", json={}).status_code == 404


def test_debug_validation_and_mock_assessment():
    with TestClient(create_app(workflow=fake_workflow())) as client:
        response = client.post("/api/v1/evaluate", json={
            "request_id": "test", "message_text": "synthetic input"})
        assert response.status_code == 200
        assert response.json()["data_mode"] == "mock"
        assert client.post("/api/v1/evaluate", json={}).status_code == 422
        assert client.post("/api/v1/evaluate", content="{bad").status_code == 422
        assert client.post("/api/v1/evaluate", json={
            "request_id": "test", "message_text": "input", "channel": "sms"}).status_code == 422
        assert client.post("/api/v1/evaluate", content="x" * 17000).status_code == 413


def test_timeout_and_sanitized_provider_failure():
    async def slow(request):
        await asyncio.sleep(1)

    async def broken(request):
        raise RuntimeError("private provider text must not escape")

    for extract, expected in [(slow, 504), (broken, 502)]:
        with TestClient(create_app(workflow=fake_workflow(
                Settings(evaluation_timeout_seconds=0.01), extract=extract))) as client:
            response = client.post("/api/v1/evaluate", json={
                "request_id": "test", "message_text": "input"})
            assert response.status_code == expected
            assert "private" not in response.text


def test_backend_caps_tools_and_rejects_correlation_mismatch():
    calls = []

    async def extract(request):
        return FakePlan(request_id=request.request_id, tasks=[
            FakeTask(kind=k) for k in ["arbitrary_api", "verify_seller", "verify_seller", "verify_seller"]])

    async def research(plan, task):
        calls.append(task.kind)
        return []

    asyncio.run(fake_workflow(extract=extract, research=research).evaluate(
        FakeRequest(request_id="test", message_text="input")))
    assert calls == ["verify_seller", "verify_seller"]

    async def mismatch(request):
        return FakePlan(request_id="wrong")

    with pytest.raises(ValueError, match="correlation"):
        asyncio.run(fake_workflow(extract=mismatch).evaluate(
            FakeRequest(request_id="test", message_text="input")))
