"""
Semantic Scholar connector.

Covers ICLR, NeurIPS, ICML, AAAI, IJCAI, CVPR, ICCV, ECCV, CHI via the
public S2 paper-search API.  An API key (SEMANTIC_SCHOLAR_KEY env var) raises
the rate limit from ~1 req/s to 10 req/s but is not required.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

_API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS   = (
    "paperId,title,abstract,authors,year,venue,"
    "externalIds,openAccessPdf,publicationVenue,fieldsOfStudy"
)

# Short venue names accepted by the S2 ?venue= filter → (canonical, rank)
_VENUES: dict[str, tuple[str, str]] = {
    "ICLR":   ("ICLR",  "A*"),
    "NeurIPS":("NeurIPS","A*"),
    "ICML":   ("ICML",  "A*"),
    "AAAI":   ("AAAI",  "A*"),
    "IJCAI":  ("IJCAI", "A*"),
    "CVPR":   ("CVPR",  "A*"),
    "ICCV":   ("ICCV",  "A*"),
    "ECCV":   ("ECCV",  "A*"),
    "CHI":    ("CHI",   "A*"),
}

# Throttle: unauthenticated = ~1 req/s; with key = 10 req/s
_SLEEP_NO_KEY  = 1.1
_SLEEP_WITH_KEY = 0.15


class SemanticScholarConnector(BaseConnector):
    """Fetches papers from top CS conferences via the Semantic Scholar API."""

    def __init__(self, venues: list[str] | None = None) -> None:
        self._key    = os.getenv("SEMANTIC_SCHOLAR_KEY", "")
        self._venues = venues or list(_VENUES.keys())
        self._sleep  = _SLEEP_WITH_KEY if self._key else _SLEEP_NO_KEY

    @property
    def source_name(self) -> str:
        return "semantic_scholar"

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        """Fetch *query* across all configured venues."""
        all_papers: list[Paper] = []
        seen: set[str] = set()
        per_venue = max(10, max_results // len(self._venues))

        for venue_key in self._venues:
            try:
                papers = self._fetch_venue(query, venue_key, per_venue)
                for p in papers:
                    if p.id not in seen:
                        seen.add(p.id)
                        all_papers.append(p)
            except Exception as exc:
                log.warning("[s2] venue=%s query='%s' failed: %s", venue_key, query, exc)
            time.sleep(self._sleep)

        return all_papers

    def fetch_venue(self, query: str, venue_key: str, max_results: int = 100) -> list[Paper]:
        """Fetch from a single venue by its short name (e.g. 'ICLR')."""
        return self._fetch_venue(query, venue_key, max_results)

    # ── internal ──────────────────────────────────────────────────────────────

    def _fetch_venue(self, query: str, venue_key: str, max_results: int) -> list[Paper]:
        venue_name, rank = _VENUES.get(venue_key, (venue_key, ""))
        params: dict[str, Any] = {
            "query":  query,
            "venue":  venue_key,
            "limit":  min(max_results, 100),
            "fields": _FIELDS,
        }
        url = f"{_API_BASE}?{urllib.parse.urlencode(params)}"
        headers: dict[str, str] = {"User-Agent": "ResearchScope/1.0"}
        if self._key:
            headers["x-api-key"] = self._key

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        return [
            p for p in (
                self._record_to_paper(r, venue_name, rank)
                for r in data.get("data", [])
            )
            if p is not None
        ]

    def _record_to_paper(
        self,
        rec: dict[str, Any],
        venue_name: str,
        rank: str,
    ) -> Paper | None:
        title = (rec.get("title") or "").strip()
        if not title:
            return None

        abstract = (rec.get("abstract") or "").replace("\n", " ").strip()
        year     = rec.get("year") or 0
        s2_id    = rec.get("paperId", "")

        # Authors
        authors = [
            a.get("name", "") for a in (rec.get("authors") or [])
            if a.get("name")
        ]

        # URL — prefer open-access PDF landing page
        ext_ids    = rec.get("externalIds") or {}
        doi        = ext_ids.get("DOI", "")
        arxiv_id   = ext_ids.get("ArXiv", "")
        oa         = rec.get("openAccessPdf") or {}
        pdf_url    = oa.get("url", "")

        if arxiv_id:
            paper_url = f"https://arxiv.org/abs/{arxiv_id}"
        elif doi:
            paper_url = f"https://doi.org/{doi}"
        elif s2_id:
            paper_url = f"https://www.semanticscholar.org/paper/{s2_id}"
        else:
            paper_url = ""

        # Tags from fields of study
        fos  = rec.get("fieldsOfStudy") or []
        tags = [f for f in fos if isinstance(f, str)][:4]

        return Paper(
            id=f"s2:{s2_id}",
            source=self.source_name,
            source_type="conference",
            title=title,
            abstract=abstract,
            authors=authors,
            year=int(year),
            published_date=f"{year}-01-01" if year else "",
            venue=venue_name,
            conference_rank=rank,
            paper_url=paper_url,
            pdf_url=pdf_url,
            tags=tags,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
