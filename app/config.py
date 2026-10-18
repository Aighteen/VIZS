"""Local configuration; loading never enables paid calls by itself."""
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    evaluation_timeout_seconds: float = 100
    grok_timeout_seconds: float = 30
    max_research_calls: int = 2
    max_jobs: int = 32
    dedupe_capacity: int = 1024
    dedupe_ttl_seconds: float = 3600
    max_callback_bytes: int = 16384
    enable_mock_sms: bool = False
    provider_mode: str = "offline"
    extension_token: str = field(default="", repr=False)
    extension_origins: tuple[str, ...] = ()
    extension_requests_per_minute: int = 6
    extension_max_inflight: int = 1
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
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 1 or v > 60
               for v in (self.extension_requests_per_minute, self.extension_max_inflight)):
            raise ValueError("Extension limits must be integers in 1..60")
        if any(not re.fullmatch(r"chrome-extension://[a-p]{32}", origin) for origin in self.extension_origins):
            raise ValueError("Extension origins must be exact Chrome extension origins")
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
        def integer(name, default):
            try:
                return int(value(name, str(default)))
            except ValueError:
                raise ValueError(f"{name} must be an integer") from None
        mock = value("VIZS_ENABLE_MOCK_SMS", "false").lower()
        if mock not in {"true", "false"}:
            raise ValueError("VIZS_ENABLE_MOCK_SMS must be true or false")
        return cls(grok_timeout_seconds=seconds("VIZS_GROK_TIMEOUT_SECONDS", 30),
                   evaluation_timeout_seconds=seconds("VIZS_EVALUATION_TIMEOUT_SECONDS", 100),
                   extension_token=value("VIZS_EXTENSION_TOKEN"),
                   extension_origins=tuple(v.strip() for v in value("VIZS_EXTENSION_ORIGINS").split(",") if v.strip()),
                   extension_requests_per_minute=integer("VIZS_EXTENSION_REQUESTS_PER_MINUTE", 6),
                   extension_max_inflight=integer("VIZS_EXTENSION_MAX_INFLIGHT", 1),
                   provider_mode=value("VIZS_PROVIDER_MODE", "offline"),
                   enable_mock_sms=mock == "true", xai_api_key=value("XAI_API_KEY"),
                   xai_model=value("XAI_MODEL"), tavily_api_key=value("TAVILY_API_KEY"))
