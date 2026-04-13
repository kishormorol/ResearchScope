"""Semantic Scholar paper collector."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from researchscope.models.paper import Paper

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_PAPER_FIELDS = (
    "paperId,title,abstract,authors,year,citationCount,externalIds,url"
)


class SemanticScholarCollector:
    """Fetch papers and author info from the Semantic Scholar Graph API."""

    def __init__(self, api_key: str | None = None, timeout: float = 15.0) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.Client(headers=headers, timeout=timeout)

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Paper]:
        """Search Semantic Scholar and return a list of :class:`Paper` objects.

        Args:
            query: Free-text search query.
            limit: Number of results to return (max 100).
            offset: Pagination offset.

        Returns:
            List of matching papers.
        """
        limit = min(limit, 100)
        params = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "fields": _PAPER_FIELDS,
        }
        response = self._client.get(f"{_BASE_URL}/paper/search", params=params)
        response.raise_for_status()
        data = response.json()
        return [self._item_to_paper(item) for item in data.get("data", [])]

    def get_paper(self, paper_id: str) -> Paper:
        """Retrieve a single paper by its Semantic Scholar paper ID."""
        response = self._client.get(
            f"{_BASE_URL}/paper/{paper_id}",
            params={"fields": _PAPER_FIELDS},
        )
        response.raise_for_status()
        return self._item_to_paper(response.json())

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> SemanticScholarCollector:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _item_to_paper(item: dict[str, Any]) -> Paper:
        year: int | None = item.get("year")
        published = date(year, 1, 1) if year else None
        authors = [a.get("name", "") for a in item.get("authors", [])]
        external = item.get("externalIds") or {}
        arxiv_id = external.get("ArXiv", "")
        paper_id = arxiv_id or item.get("paperId", "")
        url = item.get("url") or (
            f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
        )
        return Paper(
            paper_id=paper_id,
            title=item.get("title") or "",
            abstract=item.get("abstract") or "",
            authors=authors,
            published=published,
            url=url,
            source="semantic_scholar",
            citation_count=item.get("citationCount") or 0,
        )
