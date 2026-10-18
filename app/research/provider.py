"""Provider-neutral records. No provider summaries are treated as facts."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class SourceRecord:
    source_url: str
    title: str
    excerpt: str
    retrieved_at: datetime
    provider: str = "tavily"
    content_kind: str = "search_snippet"


class ResearchUnavailable(Exception):
    """Controlled provider failure without response bodies or credentials."""
    def __init__(self, message: str, *, reason: str = "unavailable"):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class SearchResponse:
    records: list[SourceRecord]
    records_received: int



class SearchProvider(Protocol):
    async def search(self, query: str) -> list[SourceRecord]: ...
