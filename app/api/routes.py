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
            "photon_enabled": False}


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
        raise HTTPException(503, "D contracts and B/C/D dependencies are not wired")
    return workflow


@router.post("/api/v1/evaluate")
async def evaluate(request: Request):
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


@router.post("/webhooks/photon")
async def photon():
    # Deliberate local disabled response, NOT a claimed Photon ACK/retry contract.
    raise HTTPException(503, "Photon contract unverified; live callbacks disabled")


@router.post("/api/v1/mock/messages", status_code=202)
async def mock_message(request: Request):
    if not request.app.state.settings.enable_mock_sms:
        raise HTTPException(404)
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
