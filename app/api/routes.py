from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.adapters.mock import MockInbound
from app.workflow.jobs import CapacityExceeded
from app.workflow.service import WorkflowUnavailable


router = APIRouter()


@router.get("/healthz")
async def health(request: Request):
    return {"status": "ok", "evaluation_ready": request.app.state.workflow is not None,
            "photon_enabled": False, "provider_mode": request.app.state.settings.provider_mode}


async def limited_body(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > request.app.state.settings.max_callback_bytes:
            raise HTTPException(413, "Request too large")
    return bytes(body)


def workflow_for(request: Request):
    workflow = request.app.state.workflow
    if workflow is None:
        raise HTTPException(503, "Evaluation workflow is not running")
    return workflow


def require_json(request: Request):
    # A declared oversized body is refused without reading it (limited_body
    # still enforces the cap for chunked or undeclared bodies).
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > request.app.state.settings.max_callback_bytes:
        raise HTTPException(413, "Request too large")
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(415, "Content-Type must be application/json")


def require_local_caller(request: Request):
    """Loopback developer routes are not for browsers (Q1).

    Any Origin header means a browser page sent the request, and a non-JSON
    Content-Type would allow a no-preflight cross-site POST. Both are rejected
    before the body is read or any provider work starts. The paired extension
    uses its own route with pairing, Origin and budget checks.
    """
    if "origin" in request.headers:
        raise HTTPException(403, "Browser-origin requests are not accepted on this local route")
    require_json(request)


async def run_evaluation(request: Request):
    workflow = workflow_for(request)
    try:
        value = workflow.contracts.request.model_validate_json(await limited_body(request))
        if value.channel != "debug":
            raise HTTPException(422, "Use debug channel for direct evaluation")
    except ValidationError:
        raise HTTPException(422, "Invalid shopping request") from None
    try:
        return await workflow.evaluate(value)
    except TimeoutError:
        raise HTTPException(504, "Evaluation timed out") from None
    except WorkflowUnavailable:
        raise HTTPException(503, "Evaluation dependency unavailable") from None
    except Exception:
        raise HTTPException(502, "Evaluation dependency failed") from None


@router.post("/api/v1/evaluate")
async def evaluate(request: Request):
    require_local_caller(request)
    return await run_evaluation(request)


async def run_message_evaluation(request: Request):
    assessment = await run_evaluation(request)
    body = request.app.state.format_sms(assessment)
    if assessment.decision == "NEED_MORE_INFORMATION" and assessment.summary not in body:
        body = assessment.summary + " " + body
    return {"assessment": assessment, "message_text": body}


@router.post("/api/v1/evaluate-message")
async def evaluate_message(request: Request):
    """Loopback developer bridge; Photon authentication stays in its SDK."""
    require_local_caller(request)
    return await run_message_evaluation(request)


@router.post("/api/v1/extension/evaluate")
async def extension_evaluate(request: Request):
    access = request.app.state.extension_access
    access.authenticate(request.headers)
    require_json(request)
    async with access.permit():
        return await run_message_evaluation(request)


@router.post("/webhooks/photon")
async def photon():
    # Deliberate local disabled response, NOT a claimed Photon ACK/retry contract.
    raise HTTPException(503, "Photon contract unverified; live callbacks disabled")


@router.post("/api/v1/mock/messages", status_code=202)
async def mock_message(request: Request):
    if not request.app.state.settings.enable_mock_sms:
        raise HTTPException(404)
    # Same browser lockdown as the loopback evaluate routes (Q7): Origin -> 403,
    # declared oversize -> 413, non-JSON -> 415, all before the body is read.
    require_local_caller(request)
    workflow = workflow_for(request)
    try:
        event = MockInbound.model_validate_json(await limited_body(request))
    except ValidationError:
        raise HTTPException(422, "Invalid local mock event") from None

    async def run():
        value = workflow.contracts.request.model_validate({
            "request_id": str(uuid4()), "message_text": event.text, "channel": "sms"})
        assessment = await workflow.evaluate(value)
        body = "MOCK SIMULATION: " + request.app.state.format_sms(assessment)
        result = await request.app.state.transport.send_text("local-simulator", body, event.event_id)
        if not result.accepted:
            raise WorkflowUnavailable("Mock send rejected")

    try:
        created = await request.app.state.jobs.submit(event.event_id, run)
    except CapacityExceeded:
        raise HTTPException(503, "Local job capacity exhausted") from None
    return {"data_mode": "mock", "scheduled": created}
