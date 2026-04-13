"""
OpenReview connector.

Covers COLM and any other venue hosted on openreview.net that is not yet
well-indexed by Semantic Scholar.  Uses the public OpenReview API v2
(no authentication required for public venues).
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

_API_BASE = "https://api2.openreview.net"

# group ID → (canonical venue name, rank, year)
_GROUPS: dict[str, tuple[str, str, int]] = {
    "colmweb.org/COLM/2024/Conference":  ("COLM", "A*", 2024),
    "ICLR.cc/2025/Conference":           ("ICLR", "A*", 2025),
    "ICLR.cc/2024/Conference":           ("ICLR", "A*", 2024),
    "NeurIPS.cc/2024/Conference":        ("NeurIPS", "A*", 2024),
}

# Default: only venues not well-covered by Semantic Scholar
_DEFAULT_GROUPS = ["colmweb.org/COLM/2024/Conference"]


class OpenReviewConnector(BaseConnector):
    """Fetches papers from OpenReview-hosted conferences."""

    def __init__(self, groups: list[str] | None = None) -> None:
        self._groups = groups or _DEFAULT_GROUPS

    @property
    def source_name(self) -> str:
        return "openreview"

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        all_papers: list[Paper] = []
        seen: set[str] = set()
        per_group = max(10, max_results // len(self._groups))

        for group in self._groups:
            try:
                papers = self._fetch_group(query, group, per_group)
                for p in papers:
                    if p.id not in seen:
                        seen.add(p.id)
                        all_papers.append(p)
            except Exception as exc:
                log.warning("[openreview] group=%s query='%s' failed: %s", group, query, exc)

        return all_papers

    # ── internal ──────────────────────────────────────────────────────────────

    def _fetch_group(self, query: str, group: str, max_results: int) -> list[Paper]:
        venue_name, rank, year = _GROUPS.get(group, ("Unknown", "", 0))

        # Use the notes/search endpoint for keyword queries within a group
        params = urllib.parse.urlencode({
            "term":   query,
            "source": "forum",
            "group":  group,
            "limit":  min(max_results, 100),
            "offset": 0,
        })
        url = f"{_API_BASE}/notes/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            notes = data.get("notes", [])
        except Exception:
            # Fall back to listing accepted notes directly
            notes = self._fetch_accepted(group, max_results)

        return [
            p for p in (
                self._note_to_paper(n, venue_name, rank, year) for n in notes
            )
            if p is not None
        ]

    def _fetch_accepted(self, group: str, max_results: int) -> list[dict]:
        """Fallback: fetch notes by venueid (returns accepted papers)."""
        venue_name, rank, year = _GROUPS.get(group, ("Unknown", "", 0))
        # venueid is the group ID for most OpenReview conferences
        params = urllib.parse.urlencode({
            "content.venueid": group,
            "limit": min(max_results, 100),
            "offset": 0,
        })
        url = f"{_API_BASE}/notes?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("notes", [])

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
            # OpenReview v2 wraps values: {"value": ...}
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
