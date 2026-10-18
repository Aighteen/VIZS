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


class SearchProvider(Protocol):
    async def search(self, query: str) -> list[SourceRecord]: ...
