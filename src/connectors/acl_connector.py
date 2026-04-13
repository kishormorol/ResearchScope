"""ACL Anthology connector."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

_ACL_SEARCH_URL = "https://aclanthology.org/api/search/"


class ACLAnthologyConnector(BaseConnector):
    """Fetches papers from the ACL Anthology search API."""

    @property
    def source_name(self) -> str:
        return "acl_anthology"

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        try:
            return self._fetch(query, max_results)
        except Exception:
            return []

    def _fetch(self, query: str, max_results: int) -> list[Paper]:
        params = {"query": query, "page_size": max_results}
        resp = requests.get(_ACL_SEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        # The API returns {"results": [...]} or a bare list
        if isinstance(payload, dict):
            results = payload.get("results", [])
        elif isinstance(payload, list):
            results = payload
        else:
            return []

        papers: list[Paper] = []
        for item in results[:max_results]:
            paper = self._item_to_paper(item)
            if paper.title:
                papers.append(paper)
        return papers

    def _item_to_paper(self, item: dict) -> Paper:
        acl_id: str = item.get("acl_id", "") or item.get("id", "")
        title: str = item.get("title", "") or ""
        abstract: str = item.get("abstract", "") or ""

        # Authors may be list of strings or list of dicts
        raw_authors = item.get("authors", []) or []
        authors: list[str] = []
        for a in raw_authors:
            if isinstance(a, str):
                authors.append(a)
            elif isinstance(a, dict):
                full = f"{a.get('first', '')} {a.get('last', '')}".strip()
                if full:
                    authors.append(full)

        year_raw = item.get("year", 0)
        try:
            year = int(year_raw) if year_raw else 0
        except (ValueError, TypeError):
            year = 0

        venue: str = item.get("venue", "") or item.get("booktitle", "") or "ACL Anthology"
        url: str = f"https://aclanthology.org/{acl_id}" if acl_id else ""
        pdf_url: str = item.get("pdf", "") or (f"{url}.pdf" if url else "")

        return Paper(
            id=f"acl:{acl_id}" if acl_id else f"acl:{hash(title)}",
            title=title.strip(),
            abstract=abstract.strip(),
            authors=authors,
            year=year,
            venue=venue,
            url=url,
            pdf_url=pdf_url,
            source=self.source_name,
            tags=["NLP"],
            difficulty="intermediate",
            citations=0,
            read_first_score=0.0,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
