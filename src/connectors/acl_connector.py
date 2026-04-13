"""
ACL Anthology connector.

Fetches recent papers from ACL Anthology via:
  1. The Anthology search API (primary)
  2. Per-venue JSON files (fallback)

Returns an empty list gracefully on any failure.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

# Map ACL venue short name → canonical conference rank
_VENUE_RANKS: dict[str, str] = {
    "ACL": "A*", "EMNLP": "A*", "NAACL": "A*",
    "EACL": "A", "COLING": "A", "CoNLL": "A",
    "Findings": "A", "TACL": "A", "CL": "A",
}

# ACL Anthology search endpoint
_SEARCH_URL = "https://aclanthology.org/api/search/papers/"

# Per-venue JSON endpoint template
_VENUE_URL = "https://aclanthology.org/venues/{venue}.json"

# Default venues to try
_DEFAULT_VENUES = ["acl", "emnlp", "naacl", "eacl"]


def _rank_for_venue(venue: str) -> str:
    for key, rank in _VENUE_RANKS.items():
        if key.lower() in venue.lower():
            return rank
    return ""


class ACLAnthologyConnector(BaseConnector):
    """Fetches papers from the ACL Anthology."""

    @property
    def source_name(self) -> str:
        return "acl_anthology"

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        # Try search API first
        try:
            papers = self._fetch_search(query, max_results)
            if papers:
                return papers
        except Exception as exc:
            log.debug("ACL search API failed: %s", exc)

        # Fallback: per-venue JSON files (ignore query, return recent papers)
        try:
            return self._fetch_venues(max_results)
        except Exception as exc:
            log.debug("ACL venue JSON fallback failed: %s", exc)

        return []

    # ── Strategy 1: search API ────────────────────────────────────────────────

    def _fetch_search(self, query: str, max_results: int) -> list[Paper]:
        params = urllib.parse.urlencode({"q": query, "page_size": max_results})
        url = f"{_SEARCH_URL}?{params}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ResearchScope/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        if isinstance(payload, dict):
            results = payload.get("results", payload.get("papers", []))
        elif isinstance(payload, list):
            results = payload
        else:
            return []

        papers = []
        for item in results[:max_results]:
            p = self._item_to_paper(item)
            if p.title:
                papers.append(p)
        return papers

    # ── Strategy 2: venue JSON ────────────────────────────────────────────────

    def _fetch_venues(self, max_results: int) -> list[Paper]:
        papers: list[Paper] = []
        per_venue = max(max_results // len(_DEFAULT_VENUES), 5)

        for venue in _DEFAULT_VENUES:
            try:
                url = _VENUE_URL.format(venue=venue)
                req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                # The venue JSON is typically a list of paper IDs or objects
                items = data if isinstance(data, list) else data.get("papers", [])
                # Take the most recent entries
                for item in items[-per_venue:]:
                    p = self._item_to_paper(item if isinstance(item, dict) else {"acl_id": item})
                    if p.title:
                        papers.append(p)
            except Exception as exc:
                log.debug("Venue '%s' fetch failed: %s", venue, exc)
                continue

        return papers

    # ── Normalise ─────────────────────────────────────────────────────────────

    def _item_to_paper(self, item: dict) -> Paper:
        acl_id: str = item.get("acl_id", "") or item.get("id", "") or item.get("url", "")
        title: str = item.get("title", "") or ""
        abstract: str = item.get("abstract", "") or ""

        # Authors: list[str] or list[dict]
        raw_authors = item.get("authors", []) or []
        authors: list[str] = []
        affiliations: list[str] = []
        for a in raw_authors:
            if isinstance(a, str):
                authors.append(a)
            elif isinstance(a, dict):
                full = f"{a.get('first', '')} {a.get('last', '')}".strip()
                if full:
                    authors.append(full)
                aff = a.get("affiliations", [])
                if isinstance(aff, list):
                    affiliations.extend(aff)

        year_raw = item.get("year", 0)
        try:
            year = int(year_raw) if year_raw else 0
        except (ValueError, TypeError):
            year = 0

        venue: str = (
            item.get("venue", "")
            or item.get("booktitle", "")
            or item.get("anthology_id", "")[:3].upper()
            or "ACL Anthology"
        )
        paper_url = f"https://aclanthology.org/{acl_id}" if acl_id else ""
        pdf_url   = item.get("pdf", "") or (f"{paper_url}.pdf" if paper_url else "")

        return Paper(
            id=f"acl:{acl_id}" if acl_id else f"acl:{abs(hash(title))}",
            source=self.source_name,
            source_type="conference",
            title=title.strip(),
            abstract=abstract.strip(),
            authors=authors,
            affiliations_raw=affiliations,
            year=year,
            venue=venue,
            conference_rank=_rank_for_venue(venue),
            paper_url=paper_url,
            pdf_url=pdf_url,
            tags=["NLP"],
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
