"""
OpenReview connector.

Fetches ALL accepted papers from OpenReview-hosted conferences by querying
the official API with venueid — no keyword queries, no API key required.

Covers: ICLR, NeurIPS (2023+), COLM
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

_API_BASE = "https://api2.openreview.net"

# venueid → (canonical name, rank, year)
# Add new venues here each year
_VENUES: dict[str, tuple[str, str, int]] = {
    "ICLR.cc/2025/Conference":          ("ICLR",    "A*", 2025),
    "ICLR.cc/2024/Conference":          ("ICLR",    "A*", 2024),
    "ICLR.cc/2023/Conference":          ("ICLR",    "A*", 2023),
    "NeurIPS.cc/2024/Conference":       ("NeurIPS", "A*", 2024),
    "NeurIPS.cc/2023/Conference":       ("NeurIPS", "A*", 2023),
    "colmweb.org/COLM/2024/Conference": ("COLM",    "A*", 2024),
}

_BATCH = 1000
_DELAY = 1.0   # seconds between paginated requests


class OpenReviewConnector(BaseConnector):
    """Fetches ALL accepted papers from OpenReview conferences."""

    def __init__(self, venues: list[str] | None = None) -> None:
        self._venues = venues or list(_VENUES.keys())
        self._token: str | None = None
        # Authenticate if credentials are available in environment
        email = os.environ.get("OPENREVIEW_EMAIL", "")
        password = os.environ.get("OPENREVIEW_PASSWORD", "")
        if email and password:
            self._token = self._login(email, password)

    @property
    def source_name(self) -> str:
        return "openreview"

    # ── Called by conference-sync (fetch everything) ──────────────────────────

    def fetch_all(self) -> list[Paper]:
        """Fetch ALL accepted papers from every configured venue."""
        all_papers: list[Paper] = []
        seen: set[str] = set()
        for venue_id in self._venues:
            try:
                papers = self._fetch_venue_all(venue_id)
                log.info("[openreview] %s → %d papers", venue_id, len(papers))
                for p in papers:
                    if p.id not in seen:
                        seen.add(p.id)
                        all_papers.append(p)
            except Exception as exc:
                log.warning("[openreview] %s failed: %s", venue_id, exc)
        return all_papers

    # ── Called by daily pipeline (keyword search within a venue) ─────────────

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        """Keyword search across configured venues (used in non-sync mode)."""
        all_papers: list[Paper] = []
        seen: set[str] = set()
        per_venue = max(10, max_results // len(self._venues))
        for venue_id in self._venues:
            try:
                papers = self._fetch_venue_search(query, venue_id, per_venue)
                for p in papers:
                    if p.id not in seen:
                        seen.add(p.id)
                        all_papers.append(p)
            except Exception as exc:
                log.warning("[openreview] search %s q='%s' failed: %s", venue_id, query, exc)
        return all_papers

    # ── internals ─────────────────────────────────────────────────────────────

    def _fetch_venue_all(self, venue_id: str) -> list[Paper]:
        """Paginate through ALL notes with content.venueid == venue_id."""
        venue_name, rank, year = _VENUES.get(venue_id, ("Unknown", "", 0))
        notes: list[dict] = []
        offset = 0

        while True:
            params = urllib.parse.urlencode({
                "content.venueid": venue_id,
                "limit": _BATCH,
                "offset": offset,
            })
            data = self._get(f"{_API_BASE}/notes?{params}")
            batch = data.get("notes", [])
            notes.extend(batch)
            if len(batch) < _BATCH:
                break
            offset += _BATCH
            time.sleep(_DELAY)

        return [
            p for p in (self._note_to_paper(n, venue_name, rank, year) for n in notes)
            if p is not None
        ]

    def _fetch_venue_search(self, query: str, venue_id: str, max_results: int) -> list[Paper]:
        venue_name, rank, year = _VENUES.get(venue_id, ("Unknown", "", 0))
        params = urllib.parse.urlencode({
            "term":   query,
            "source": "forum",
            "group":  venue_id,
            "limit":  min(max_results, 100),
            "offset": 0,
        })
        try:
            data  = self._get(f"{_API_BASE}/notes/search?{params}")
            notes = data.get("notes", [])
        except Exception:
            # fallback: venueid query
            notes = self._fetch_venue_all(venue_id)[:max_results]

        return [
            p for p in (self._note_to_paper(n, venue_name, rank, year) for n in notes)
            if p is not None
        ]

    @staticmethod
    def _login(email: str, password: str) -> str | None:
        """Authenticate and return a bearer token."""
        payload = json.dumps({"id": email, "password": password}).encode()
        req = urllib.request.Request(
            f"{_API_BASE}/login",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ResearchScope/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                token = json.loads(resp.read()).get("token", "")
                if token:
                    log.info("[openreview] authenticated successfully")
                return token or None
        except Exception as exc:
            log.warning("[openreview] login failed: %s", exc)
            return None

    def _get(self, url: str) -> dict:
        headers = {"User-Agent": "ResearchScope/1.0"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def _note_to_paper(
        self,
        note: dict[str, Any],
        venue_name: str,
        rank: str,
        year: int,
    ) -> Paper | None:
        content = note.get("content", {})

        def val(key: str) -> Any:
            v = content.get(key, "")
            return v.get("value", "") if isinstance(v, dict) else v

        title = str(val("title") or "").strip()
        if not title:
            return None

        abstract = str(val("abstract") or "").replace("\n", " ").strip()

        authors_raw = val("authors") or []
        authors = (
            [str(a) for a in authors_raw]
            if isinstance(authors_raw, list)
            else [str(authors_raw)]
        )

        keywords_raw = val("keywords") or []
        tags = (
            [str(k) for k in keywords_raw[:5]]
            if isinstance(keywords_raw, list)
            else []
        )

        note_id   = note.get("id", "")
        paper_url = f"https://openreview.net/forum?id={note_id}" if note_id else ""

        return Paper(
            id=f"openreview:{note_id}",
            source=self.source_name,
            source_type="conference",
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            published_date=f"{year}-01-01",
            venue=venue_name,
            conference_rank=rank,
            paper_url=paper_url,
            tags=tags,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
