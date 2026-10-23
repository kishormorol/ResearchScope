"""
OpenReview connector.

Fetches ALL accepted papers from OpenReview-hosted conferences by querying
the official API with venueid — no keyword queries, no API key required.

Covers: ICLR, NeurIPS, ICML, COLM

Each accepted note carries its acceptance tier in `content.venue`
(e.g. "NeurIPS 2025 spotlight", "ICLR 2025 Oral", "ICML 2024 Poster"). We parse
that into `Paper.presentation_type` so the scorer can reward oral/spotlight
papers (the top decile of accepted work).
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
    "ICLR.cc/2026/Conference":          ("ICLR",    "A*", 2026),
    "ICLR.cc/2025/Conference":          ("ICLR",    "A*", 2025),
    "ICLR.cc/2024/Conference":          ("ICLR",    "A*", 2024),
    "ICLR.cc/2023/Conference":          ("ICLR",    "A*", 2023),
    "ICLR.cc/2022/Conference":          ("ICLR",    "A*", 2022),
    "NeurIPS.cc/2025/Conference":       ("NeurIPS", "A*", 2025),
    "NeurIPS.cc/2024/Conference":       ("NeurIPS", "A*", 2024),
    "NeurIPS.cc/2023/Conference":       ("NeurIPS", "A*", 2023),
    "NeurIPS.cc/2022/Conference":       ("NeurIPS", "A*", 2022),
    "ICML.cc/2025/Conference":          ("ICML",    "A*", 2025),
    "ICML.cc/2024/Conference":          ("ICML",    "A*", 2024),
    "colmweb.org/COLM/2025/Conference": ("COLM",    "A*", 2025),
    "colmweb.org/COLM/2024/Conference": ("COLM",    "A*", 2024),
}

# Acceptance tiers as they appear in content.venue. OpenReview casing is
# inconsistent across venues ("Oral" vs "oral"), so matching is case-insensitive.
_TIERS = ("oral", "spotlight", "poster")


def _parse_presentation_type(venue_str: str) -> str:
    """Extract the acceptance tier from a `content.venue` string."""
    low = venue_str.lower()
    for tier in _TIERS:
        if tier in low:
            return tier
    return ""


def _epoch_ms_to_iso_date(ms: Any) -> str:
    """Convert an OpenReview epoch-millis timestamp to an ISO date (YYYY-MM-DD)."""
    if not isinstance(ms, (int, float)) or ms <= 0:
        return ""
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, OverflowError, OSError):
        return ""

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

    def fetch_all(self, skip_keys: set[str] | None = None) -> list[Paper]:
        """Fetch ALL accepted papers from every configured venue.

        ``skip_keys`` holds "<venue>:<year>" blocks already in the complete
        archive (settled past years); those venue/years are skipped to avoid
        re-downloading immutable proceedings every sync.
        """
        skip_keys = skip_keys or set()
        all_papers: list[Paper] = []
        seen: set[str] = set()
        for venue_id in self._venues:
            name, _rank, year = _VENUES.get(venue_id, ("Unknown", "", 0))
            if f"{name}:{year}" in skip_keys:
                log.info("[openreview] %s (%s %s) archived — skipping", venue_id, name, year)
                continue
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
        return all_papers[:max_results]

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
            return self._fetch_venue_all(venue_id)[:max_results]

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

        # Do NOT pass raw OpenReview author keywords as tags — they are free-form
        # and would create thousands of junk topics. The tagger (Stage 3) assigns
        # normalized taxonomy tags from title+abstract instead.
        tags: list[str] = []

        # Acceptance tier (oral / spotlight / poster) lives in content.venue,
        # e.g. "NeurIPS 2025 spotlight". The bare venueid carries no tier.
        presentation_type = _parse_presentation_type(str(val("venue") or ""))

        # Prefer the real publication timestamp; fall back to camera-ready /
        # creation date, then to Jan 1 of the venue year as a last resort.
        published_date = (
            _epoch_ms_to_iso_date(note.get("pdate"))
            or _epoch_ms_to_iso_date(note.get("odate"))
            or _epoch_ms_to_iso_date(note.get("cdate"))
            or f"{year}-01-01"
        )

        note_id   = note.get("id", "")
        paper_url = f"https://openreview.net/forum?id={note_id}" if note_id else ""

        # content.pdf is a site-relative path like "/pdf/<hash>.pdf".
        pdf_path = str(val("pdf") or "")
        pdf_url = f"https://openreview.net{pdf_path}" if pdf_path.startswith("/") else ""

        return Paper(
            id=f"openreview:{note_id}",
            source=self.source_name,
            source_type="conference",
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            published_date=published_date,
            venue=venue_name,
            conference_rank=rank,
            presentation_type=presentation_type,
            paper_url=paper_url,
            pdf_url=pdf_url,
            tags=tags,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
