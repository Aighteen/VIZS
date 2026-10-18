"""QA security/access tests (API-01..03, PH backend, SEC-01). SYNTHETIC data only;
mocked transports; no network, DNS, real keys or messages."""
import asyncio
import logging
import re
import socket
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.access import ExtensionAccess
from app.config import Settings
from app.decision import decide
from app.main import create_app
from app.models import Assessment, OrchestratorPlan, ShoppingRequest, VerifiedInboundMessage
from app.services.grok import XAICompletionClient
from app.services.tavily import TavilyProvider
from app.workflow.service import Contracts, EvaluationWorkflow
from tests.test_qa_acceptance import (CONFLICT_EXTRACT, CONFLICT_ROW, CONFLICT_SEARCH, LISTING, TAVILY_KEY, TOKEN,
                                      XAI_KEY, Harness, live_settings)

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORIGIN = "chrome-extension://" + "a" * 32
PAYLOAD = {"request_id": "qa-sec", "message_text": f"Check {LISTING}", "channel": "debug"}


# ---------------------------------------------------------------- API-01

@pytest.mark.parametrize("settings_token,headers,expected", [
    ("", {"Authorization": f"Bearer {TOKEN}"}, 503),
    (TOKEN, {}, 401),
    (TOKEN, {"Authorization": "Bearer wrong-token"}, 401),
    (TOKEN, {"Authorization": TOKEN}, 401),
    (TOKEN, {"Authorization": f"bearer {TOKEN}"}, 401),
    (TOKEN, {"Authorization": f"Bearer {TOKEN}", "Origin": "https://hostile-shop.com"}, 403),
    (TOKEN, {"Authorization": f"Bearer {TOKEN}", "Origin": "null"}, 403),
    (TOKEN, {"Authorization": f"Bearer {TOKEN}", "Origin": "chrome-extension://" + "b" * 32}, 403),
], ids=["unconfigured", "missing", "wrong", "no_scheme", "lowercase_scheme", "web_origin",
        "null_origin", "other_extension"])
def test_API_01_rejected_extension_requests_make_no_provider_or_dns_calls(settings_token, headers, expected):
    harness = Harness(settings=live_settings(extension_token=settings_token, extension_origins=(ALLOWED_ORIGIN,)))
    response = harness.post(path="/api/v1/extension/evaluate", headers=headers)
    assert response.status_code == expected
    assert harness.calls == [] and harness.dns == []
    for secret in (TOKEN, XAI_KEY, TAVILY_KEY):
        assert secret not in response.text


def test_API_01_auth_precedes_body_parsing_and_oversized_bodies_get_413():
    harness = Harness(settings=live_settings(extension_origins=(ALLOWED_ORIGIN,)))
    big = b'{"request_id":"x","message_text":"' + b"a" * 20000 + b'","channel":"debug"}'
    with TestClient(harness.app()) as client:
        assert client.post("/api/v1/extension/evaluate", content=big).status_code == 401
        response = client.post("/api/v1/extension/evaluate", content=big,
                               headers={"Authorization": f"Bearer {TOKEN}", "Origin": ALLOWED_ORIGIN})
        assert response.status_code == 413
        for path in ["/api/v1/evaluate", "/api/v1/evaluate-message"]:
            assert client.post(path, content=big).status_code == 413
        # Q1 decision: the extension route requires application/json (415 otherwise).
        assert client.post("/api/v1/extension/evaluate", content=b"{bad",
                           headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 415
        assert client.post("/api/v1/extension/evaluate", content=b"{bad",
                           headers={"Authorization": f"Bearer {TOKEN}",
                                    "Content-Type": "application/json"}).status_code == 422
        assert client.post("/api/v1/extension/evaluate", json={**PAYLOAD, "channel": "extension"},
                           headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 422
    assert harness.calls == [] and harness.dns == []


def test_API_01_allowed_origin_succeeds_and_cors_is_exact():
    harness = Harness(settings=live_settings(extension_origins=(ALLOWED_ORIGIN,)), search=CONFLICT_SEARCH,
                      extract=CONFLICT_EXTRACT, promise={"records": [CONFLICT_ROW]})
    with TestClient(harness.app()) as client:
        ok = client.post("/api/v1/extension/evaluate", json=PAYLOAD,
                         headers={"Authorization": f"Bearer {TOKEN}", "Origin": ALLOWED_ORIGIN})
        assert ok.status_code == 200
        assert ok.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
        preflight = client.options("/api/v1/extension/evaluate", headers={
            "Origin": "https://hostile-shop.com", "Access-Control-Request-Method": "POST"})
        assert preflight.headers.get("access-control-allow-origin") != "https://hostile-shop.com"
        assert preflight.headers.get("access-control-allow-origin") != "*"


# ---------------------------------------------------------------- API-02

def _blocking_workflow(settings, started, release, calls):
    async def extract(request):
        calls.append(request.request_id)
        started.set()
        await release.wait()
        return OrchestratorPlan(request_id=request.request_id, intent="need_more_information",
                                requires_user_input=True, clarification="SYNTHETIC", data_mode="mock")

    async def research(plan, task):
        raise AssertionError("no research for clarification")
    return EvaluationWorkflow(Contracts(ShoppingRequest, OrchestratorPlan, Assessment), extract, research,
                              decide, settings)


def test_API_02_concurrent_inflight_request_rejected_before_provider_work():
    async def scenario():
        settings = Settings(extension_token=TOKEN, extension_max_inflight=1, extension_requests_per_minute=6)
        started, release, calls = asyncio.Event(), asyncio.Event(), []
        app = create_app(settings=settings, workflow=_blocking_workflow(settings, started, release, calls))
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://qa.local") as client:
            first = asyncio.create_task(client.post("/api/v1/extension/evaluate", json={**PAYLOAD, "request_id": "a"}, headers=headers))
            await asyncio.wait_for(started.wait(), 2)
            second = await client.post("/api/v1/extension/evaluate", json={**PAYLOAD, "request_id": "b"}, headers=headers)
            assert second.status_code == 429 and second.headers["retry-after"] == "60"
            release.set()
            assert (await first).status_code == 200
            third = await client.post("/api/v1/extension/evaluate", json={**PAYLOAD, "request_id": "c"}, headers=headers)
            assert third.status_code == 200
        assert calls == ["a", "c"]
    asyncio.run(scenario())


def test_API_02_rate_window_is_bounded_and_resets():
    async def scenario():
        clock = [0.0]
        gate = ExtensionAccess(Settings(extension_token=TOKEN, extension_requests_per_minute=2, extension_max_inflight=5),
                               clock=lambda: clock[0])
        from fastapi import HTTPException
        for _ in range(2):
            async with gate.permit():
                pass
        with pytest.raises(HTTPException) as error:
            async with gate.permit():
                pass
        assert error.value.status_code == 429
        clock[0] = 59.9
        with pytest.raises(HTTPException):
            async with gate.permit():
                pass
        clock[0] = 60.0
        async with gate.permit():
            pass
    asyncio.run(scenario())


@pytest.mark.parametrize("bad", [dict(extension_requests_per_minute=0), dict(extension_requests_per_minute=61),
                                 dict(extension_max_inflight=0), dict(extension_origins=("chrome-extension://*",)),
                                 dict(extension_origins=("https://shop.com",))])
def test_API_02_unbounded_or_wildcard_policy_configuration_rejected(bad):
    with pytest.raises(ValueError):
        Settings(**bad)


# ---------------------------------------------------------------- EXT-03/04 (backend side)

def test_EXT_03_04_backend_distinguishes_insufficient_result_from_failures_without_retry():
    attempts = []

    def workflow_for(mode, settings):
        async def extract(request):
            attempts.append(mode)
            if mode == "error":
                raise RuntimeError("QA-PRIVATE provider detail")
            if mode == "slow":
                await asyncio.sleep(1)
            return OrchestratorPlan(request_id=request.request_id, intent="evaluate_purchase", product_url=LISTING,
                                    tasks=[{"kind": "verify_seller", "query": "x"}], data_mode="mock")

        async def research(plan, task):
            return []
        return EvaluationWorkflow(Contracts(ShoppingRequest, OrchestratorPlan, Assessment), extract, research,
                                  decide, settings)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    for mode, expected in [("insufficient", 200), ("error", 502), ("slow", 504)]:
        settings = Settings(extension_token=TOKEN, evaluation_timeout_seconds=0.05)
        app = create_app(settings=settings, workflow=workflow_for(mode, settings))
        with TestClient(app) as client:
            response = client.post("/api/v1/extension/evaluate", json=PAYLOAD, headers=headers)
            assert response.status_code == expected
            assert "QA-PRIVATE" not in response.text
            if expected == 200:
                assert response.json()["assessment"]["decision"] == "VERIFY_FIRST"
                assert response.json()["assessment"]["seller_risk"] == "INSUFFICIENT_EVIDENCE"
            assert app.state.extension_access.active == 0, "failed work must release the in-flight budget"
    assert attempts == ["insufficient", "error", "slow"], "no automatic retry of failed provider work"


# ---------------------------------------------------------------- API-03

def test_API_03_offline_with_populated_keys_makes_no_network_or_dns_calls(monkeypatch):
    sockets = []

    def forbidden_socket(*args, **kwargs):
        sockets.append(args[:1])
        raise AssertionError("offline mode must not touch the network")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden_socket)
    monkeypatch.setattr(socket, "create_connection", forbidden_socket)
    harness = Harness(settings=Settings(provider_mode="offline", xai_api_key=XAI_KEY, xai_model="qa-synthetic-model",
                                        tavily_api_key=TAVILY_KEY, extension_token=TOKEN))
    transport = httpx.MockTransport(harness.handler)
    app = create_app(settings=harness.settings, xai_transport=transport, tavily_transport=transport,
                     domain_transport=transport)  # default (real) destination validator: must not be invoked
    with TestClient(app) as client:
        assert client.get("/healthz").json()["provider_mode"] == "offline"
        for path, headers in [("/api/v1/evaluate", {}), ("/api/v1/evaluate-message", {}),
                              ("/api/v1/extension/evaluate", {"Authorization": f"Bearer {TOKEN}"})]:
            response = client.post(path, json={**PAYLOAD, "request_id": path}, headers=headers)
            assert response.status_code == 200
            body = response.json()
            assessment = body.get("assessment", body)
            assert "unavailable" in assessment["summary"]
            assert assessment["data_mode"] != "live"
    assert harness.calls == [] and sockets == []


# ---------------------------------------------------------------- PH (backend side)

@pytest.mark.parametrize("body", [b"", b"{}", b'{"text":"Check https://synthetic-shop.com/p"}', b"x" * 40000])
@pytest.mark.parametrize("mock_enabled", [False, True])
def test_PH_photon_webhook_is_always_503_without_echo(body, mock_enabled):
    app = create_app(settings=Settings(enable_mock_sms=mock_enabled), format_sms=lambda a: "SYNTHETIC")
    with TestClient(app) as client:
        response = client.post("/webhooks/photon", content=body,
                               headers={"X-Signature": "qa-synthetic", "Content-Type": "application/json"})
        assert response.status_code == 503
        assert "synthetic-shop.com" not in response.text
        assert len(app.state.transport.sent) == 0


def test_PH_02_mock_simulator_disabled_by_default_and_labeled_when_enabled():
    with TestClient(create_app(settings=Settings())) as client:
        assert client.post("/api/v1/mock/messages", json={"event_id": "e", "text": "t"}).status_code == 404
    app = create_app(settings=Settings(enable_mock_sms=True))
    with TestClient(app) as client:
        event = {"event_id": "qa-dup", "text": f"Check {LISTING}"}
        results = [client.post("/api/v1/mock/messages", json=event).json() for _ in range(3)]
        assert [r["scheduled"] for r in results] == [True, False, False]
        assert all(r["data_mode"] == "mock" for r in results)
        client.get("/healthz")
        assert len(app.state.transport.sent) == 1
        assert app.state.transport.sent[0][1].startswith("MOCK SIMULATION: ")


# ---------------------------------------------------------------- SEC-01

PHONE = "+1 206 555 0147"


def test_SEC_01_no_secrets_or_phone_numbers_in_logs_or_responses(caplog):
    caplog.set_level(logging.DEBUG)
    harness = Harness(search=CONFLICT_SEARCH, extract=CONFLICT_EXTRACT, promise={"records": [CONFLICT_ROW]})
    with TestClient(harness.app()) as client:
        responses = [
            client.post("/api/v1/extension/evaluate", headers={"Authorization": f"Bearer {TOKEN}"},
                        json={**PAYLOAD, "message_text": f"Text me at {PHONE} about {LISTING}"}),
            client.post("/api/v1/evaluate", json={"request_id": "x", "message_text": f"call {PHONE}", "channel": "sms"}),
            client.post("/api/v1/extension/evaluate", headers={"Authorization": "Bearer wrong"}, json=PAYLOAD),
        ]
    assert [r.status_code for r in responses] == [200, 422, 401]
    digits = re.sub(r"\D", "", PHONE)
    for text in [caplog.text, *(r.text for r in responses)]:
        for secret in (XAI_KEY, TAVILY_KEY, TOKEN):
            assert secret not in text
        assert digits not in re.sub(r"\D", "", text.replace(LISTING, ""))


def test_SEC_01_reprs_hide_credentials_and_sender_handles():
    settings = live_settings()
    client = XAICompletionClient(httpx.AsyncClient(), api_key=XAI_KEY, model="qa-synthetic-model")
    provider = TavilyProvider(TAVILY_KEY)
    message = VerifiedInboundMessage(external_message_id="m1", sender_handle=PHONE, channel="imessage",
                                     text="SYNTHETIC", received_at="2026-10-17T12:00:00Z")
    for obj in (settings, client, provider):
        for text in (repr(obj), str(obj)):
            assert XAI_KEY not in text and TAVILY_KEY not in text and TOKEN not in text
    assert PHONE not in repr(message) and PHONE not in str(message)


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git unavailable")


def test_SEC_01_no_env_files_tracked_and_env_files_ignored():
    listing = _git("ls-files")
    if listing.returncode != 0:
        pytest.skip("not a git checkout")
    tracked = listing.stdout.splitlines()
    env_files = [p for p in tracked if re.search(r"(^|/)\.env($|\.)", p) and not p.endswith(".env.example")]
    assert env_files == []
    for path in [".env", "extension/.env", "app/adapters/spectrum/.env"]:
        assert _git("check-ignore", "-q", path).returncode == 0, f"{path} must be ignored"


def test_SEC_01_tracked_files_contain_no_provider_keys_pans_or_phone_numbers():
    listing = _git("ls-files")
    if listing.returncode != 0:
        pytest.skip("not a git checkout")
    patterns = {"xai_key": r"xai-[A-Za-z0-9]{20,}", "tavily_key": r"tvly-[A-Za-z0-9]{10,}",
                "private_key": r"-----BEGIN [A-Z ]*PRIVATE KEY", "github_token": r"gh[pousr]_[A-Za-z0-9]{30,}",
                "phone": r"(?<![\w.])\+1[ .-]?\(?[2-9]\d{2}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)"}

    def luhn(digits):
        total = 0
        for i, d in enumerate(reversed(digits)):
            n = int(d) * (2 if i % 2 else 1)
            total += n - 9 if n > 9 else n
        return total % 10 == 0
    hits = []
    for name in listing.stdout.splitlines():
        if name.endswith("package-lock.json") or name.startswith("tests/test_qa_"):
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for label, p in patterns.items():
                for match in re.finditer(p, line):
                    digits = re.sub(r"\D", "", match.group())[-10:]
                    if label == "phone" and "555" in (digits[:3], digits[3:6]):
                        continue  # fictional 555 numbers used as labeled synthetic test data
                    hits.append(f"{name}:{number}:{label}")
            for match in re.finditer(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", line):
                digits = re.sub(r"\D", "", match.group())
                if 13 <= len(digits) <= 19 and luhn(digits):
                    hits.append(f"{name}:{number}:pan_like")
    assert hits == []  # path:line:label only; matched values are never printed
