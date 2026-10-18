import asyncio

import pytest
from fastapi.testclient import TestClient

from app.adapters.photon import PhotonAdapter
from app.config import Settings
from app.main import create_app
from app.workflow.service import WorkflowUnavailable
from tests.test_api import fake_workflow


def test_real_transport_fails_closed():
    adapter = PhotonAdapter()
    with pytest.raises(WorkflowUnavailable):
        asyncio.run(adapter.parse_and_verify_inbound(b"{}", {}))
    with pytest.raises(WorkflowUnavailable):
        asyncio.run(adapter.send_text("synthetic", "test", "test"))
    with TestClient(create_app()) as client:
        assert client.post("/webhooks/photon", json={"text": "not verified"}).status_code == 503


def test_local_simulator_uses_workflow_and_dedupes():
    app = create_app(settings=Settings(enable_mock_sms=True), workflow=fake_workflow(),
                     format_sms=lambda a: a.summary)
    with TestClient(app) as client:
        event = {"event_id": "synthetic-id", "text": "synthetic input"}
        first = client.post("/api/v1/mock/messages", json=event)
        assert first.status_code == 202
        assert first.json() == {"data_mode": "mock", "scheduled": True}
        assert client.post("/api/v1/mock/messages", json=event).json()["scheduled"] is False
        # Barrier on TestClient's event loop lets the already-scheduled job finish.
        client.get("/healthz")
        assert len(app.state.transport.sent) == 1
        assert app.state.transport.sent[0][1].startswith("MOCK SIMULATION:")
        assert client.post("/api/v1/mock/messages", json={}).status_code == 422


def test_mock_requires_explicit_dependencies():
    with pytest.raises(ValueError):
        create_app(settings=Settings(enable_mock_sms=True), workflow=fake_workflow())
