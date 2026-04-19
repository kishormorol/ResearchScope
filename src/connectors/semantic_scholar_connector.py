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

_API_BASE      = "https://api.semanticscholar.org/graph/v1/paper/search"
_API_BULK      = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
_FIELDS        = (
    "paperId,title,abstract,authors.name,authors.affiliations,"
    "year,venue,externalIds,openAccessPdf,publicationVenue,fieldsOfStudy"
)

# Venues to bulk-fetch in fetch_all (OpenReview is down; S2 is the fallback)
# Each entry: venue_key → years to fetch
_BULK_VENUES: dict[str, list[int]] = {
    "ICLR":    [2023, 2024, 2025],
    "NeurIPS": [2023, 2024],
    "COLM":    [2024],
}

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
    "SIGMOD": ("SIGMOD","A*"),
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

    def fetch_all(self, venues: dict[str, list[int]] | None = None) -> list[Paper]:
        """Bulk-fetch ALL papers for ICLR/NeurIPS/COLM using the S2 bulk endpoint.

        Uses cursor-based pagination — no result cap beyond API limits.
        Falls back gracefully per venue/year on failure.
        """
        target = venues or _BULK_VENUES
        all_papers: list[Paper] = []
        seen: set[str] = set()

        for venue_key, years in target.items():
            venue_name, rank = _VENUES.get(venue_key, (venue_key, ""))
            for year in years:
                try:
                    papers = self._bulk_fetch_venue_year(venue_key, venue_name, rank, year)
                    log.info("[s2] bulk %s %d → %d papers", venue_key, year, len(papers))
                    for p in papers:
                        if p.id not in seen:
                            seen.add(p.id)
                            all_papers.append(p)
                except Exception as exc:
                    log.warning("[s2] bulk %s %d failed: %s", venue_key, year, exc)

        return all_papers

    def _bulk_fetch_venue_year(
        self, venue_key: str, venue_name: str, rank: str, year: int
    ) -> list[Paper]:
        """Paginate through ALL S2 papers for a venue+year using the bulk endpoint."""
        papers: list[Paper] = []
        token: str | None = None

        while True:
            params: dict[str, Any] = {
                "query":  venue_key,
                "venue":  venue_key,
                "year":   str(year),
                "fields": _FIELDS,
                "limit":  500,
            }
            if token:
                params["token"] = token

            url = f"{_API_BULK}?{urllib.parse.urlencode(params)}"
            headers: dict[str, str] = {"User-Agent": "ResearchScope/1.0"}
            if self._key:
                headers["x-api-key"] = self._key

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())

            for rec in data.get("data", []):
                p = self._record_to_paper(rec, venue_name, rank)
                if p:
                    papers.append(p)

            token = data.get("token")
            if not token:
                break
            time.sleep(self._sleep)

        return papers

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

        # Authors + affiliations (subfield format: {name, affiliations: [...]})
        raw_authors = rec.get("authors") or []
        authors: list[str] = []
        affiliations_raw: list[str] = []
        for a in raw_authors:
            name = a.get("name", "").strip()
            if name:
                authors.append(name)
            for aff in (a.get("affiliations") or []):
                aff_str = aff.strip() if isinstance(aff, str) else str(aff).strip()
                if aff_str and aff_str not in affiliations_raw:
                    affiliations_raw.append(aff_str)

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
            affiliations_raw=affiliations_raw,
            year=int(year),
            published_date=f"{year}-01-01" if year else "",
            venue=venue_name,
            conference_rank=rank,
            paper_url=paper_url,
            pdf_url=pdf_url,
            tags=tags,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
