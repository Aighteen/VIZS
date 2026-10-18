from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    evaluation_timeout_seconds: float = 20
    max_research_calls: int = 2
    max_jobs: int = 32
    dedupe_capacity: int = 1024
    dedupe_ttl_seconds: float = 3600
    max_callback_bytes: int = 16384
    enable_mock_sms: bool = False

    def __post_init__(self):
        if any(value <= 0 for name, value in vars(self).items()
               if name != "enable_mock_sms"):
            raise ValueError("Limits must be positive")
