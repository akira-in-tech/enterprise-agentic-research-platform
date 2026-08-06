from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single search result."""

    title: str
    url: str
    content: str
    source: str


class SearchClient(Protocol):
    """Interface implemented by search providers."""

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
    ) -> list[SearchResult]: ...
