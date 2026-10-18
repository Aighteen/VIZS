"""Local configuration; loading never enables paid calls by itself."""
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    evaluation_timeout_seconds: float = 55
    grok_timeout_seconds: float = 30
    max_research_calls: int = 2
    max_jobs: int = 32
    dedupe_capacity: int = 1024
    dedupe_ttl_seconds: float = 3600
    max_callback_bytes: int = 16384
    enable_mock_sms: bool = False
    provider_mode: str = "offline"
    xai_api_key: str = field(default="", repr=False)
    xai_model: str = ""
    tavily_api_key: str = field(default="", repr=False)

    def __post_init__(self):
        limits = (self.evaluation_timeout_seconds, self.grok_timeout_seconds, self.max_research_calls,
                  self.max_jobs, self.dedupe_capacity, self.dedupe_ttl_seconds,
                  self.max_callback_bytes)
        if any(not math.isfinite(v) or v <= 0 for v in limits):
            raise ValueError("Limits must be finite and positive")
        if self.grok_timeout_seconds > 60 or self.evaluation_timeout_seconds > 120:
            raise ValueError("Provider and workflow timeouts exceed prototype limits")
        if self.provider_mode not in {"offline", "live"}:
            raise ValueError("VIZS_PROVIDER_MODE must be offline or live")

    @classmethod
    def from_env(cls, env_file=None, *, environ=None):
        # Explicit root only: do not search parents or mutate process environment.
        path = Path(env_file) if env_file is not None else Path(__file__).resolve().parents[1] / ".env"
        values = {**dotenv_values(path, interpolate=False, encoding="utf-8-sig"),
                  **(os.environ if environ is None else environ)}
        def value(name, default=""):
            return (values.get(name) or default).strip()
        def seconds(name, default):
            try:
                return float(value(name, str(default)))
            except ValueError:
                raise ValueError(f"{name} must be numeric") from None
        mock = value("VIZS_ENABLE_MOCK_SMS", "false").lower()
        if mock not in {"true", "false"}:
            raise ValueError("VIZS_ENABLE_MOCK_SMS must be true or false")
        return cls(grok_timeout_seconds=seconds("VIZS_GROK_TIMEOUT_SECONDS", 30),
                   evaluation_timeout_seconds=seconds("VIZS_EVALUATION_TIMEOUT_SECONDS", 55),
                   provider_mode=value("VIZS_PROVIDER_MODE", "offline"),
                   enable_mock_sms=mock == "true", xai_api_key=value("XAI_API_KEY"),
                   xai_model=value("XAI_MODEL"), tavily_api_key=value("TAVILY_API_KEY"))
