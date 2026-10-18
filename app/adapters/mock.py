"""Local simulator only; these fields are NOT a Photon callback contract."""
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, Field


class MockInbound(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=4000)


@dataclass(frozen=True)
class SendResult:
    accepted: bool


class MockTransport:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, destination: str, body: str, correlation_id: str):
        # No phone numbers or vendor calls; destination is a synthetic local handle.
        self.sent.append((correlation_id, body))
        return SendResult(accepted=True)
