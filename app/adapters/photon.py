"""Fail closed until account-specific Photon callback/auth/send docs are verified.

No Photon wire schema, signature header, or acknowledgement semantics is assumed.
"""
from app.workflow.service import WorkflowUnavailable


class PhotonAdapter:
    async def parse_and_verify_inbound(self, raw_bytes: bytes, headers):
        raise WorkflowUnavailable("Photon account-specific contract is unverified")

    async def send_text(self, destination: str, body: str, correlation_id: str):
        raise WorkflowUnavailable("Photon outbound transport is disabled")
