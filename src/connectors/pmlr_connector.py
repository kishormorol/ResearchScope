"""
PMLR (Proceedings of Machine Learning Research) connector.

Fetches papers from proceedings.mlr.press — no API key required.
Covers ICML and any other PMLR-hosted venue.

PMLR volume numbers:
  ICML 2024 → v235
  ICML 2023 → v202
  ICML 2022 → v162
"""
from __future__ import annotations

import logging
import re
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

_BASE = "https://proceedings.mlr.press"

# volume → (venue name, rank, year)
_VOLUMES: dict[str, tuple[str, str, int]] = {
    "235": ("ICML", "A*", 2024),
    "202": ("ICML", "A*", 2023),
    "162": ("ICML", "A*", 2022),
}

_DELAY = 2.0


class _PMLRParser(HTMLParser):
    """Extract paper records from a PMLR proceedings index page."""

    def __init__(self) -> None:
        super().__init__()
        self.papers: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._in_title = False
        self._in_authors = False
        self._in_abstract = False
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "")
        self._tag_stack.append(tag)

        if tag == "div" and "paper" in cls:
            self._current = {"title": "", "authors": [], "abstract": "", "url": ""}
        elif self._current is not None:
            if tag == "p" and cls == "title":
                self._in_title = True
            elif tag == "p" and cls == "authors":
                self._in_authors = True
            elif tag == "p" and cls == "abstract":
                self._in_abstract = True
            elif tag == "a" and self._in_title:
                href = attr_dict.get("href", "")
                if href:
                    self._current["url"] = href if href.startswith("http") else f"{_BASE}{href}"

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack:
            self._tag_stack.pop()
        if tag == "p":
            self._in_title = False
            self._in_authors = False
            self._in_abstract = False
        if tag == "div" and self._current and self._current.get("title"):
            self.papers.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self._current["title"] += text
        elif self._in_authors:
            # Authors are comma-separated inline text
            self._current["authors"] = [a.strip() for a in text.split(",") if a.strip()]
        elif self._in_abstract:
            self._current["abstract"] += " " + text


class PMLRConnector(BaseConnector):
    """Fetches ALL papers from PMLR proceedings (ICML and similar venues)."""

    def __init__(self, volumes: dict[str, tuple[str, str, int]] | None = None) -> None:
        self._volumes = volumes or _VOLUMES

    @property
    def source_name(self) -> str:
        return "pmlr"

    def fetch_all(self) -> list[Paper]:
        """Fetch ALL papers from every configured PMLR volume."""
        all_papers: list[Paper] = []
        seen: set[str] = set()
        for vol, (venue, rank, year) in self._volumes.items():
            try:
                papers = self._fetch_volume(vol, venue, rank, year)
                log.info("[pmlr] v%s (%s %d) → %d papers", vol, venue, year, len(papers))
                for p in papers:
                    if p.id not in seen:
                        seen.add(p.id)
                        all_papers.append(p)
            except Exception as exc:
                log.warning("[pmlr] v%s failed: %s", vol, exc)
            time.sleep(_DELAY)
        return all_papers

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        """Keyword filter over all papers (used in non-sync mode)."""
        q = query.lower()
        results: list[Paper] = []
        for vol, (venue, rank, year) in self._volumes.items():
            try:
                papers = self._fetch_volume(vol, venue, rank, year)
                matched = [
                    p for p in papers
                    if q in p.title.lower() or q in (p.abstract or "").lower()
                ]
                results.extend(matched[:max_results])
            except Exception as exc:
                log.warning("[pmlr] v%s fetch failed: %s", vol, exc)
            if len(results) >= max_results:
                break
        return results[:max_results]

    # ── internals ─────────────────────────────────────────────────────────────

    def _fetch_volume(self, volume: str, venue: str, rank: str, year: int) -> list[Paper]:
        url = f"{_BASE}/v{volume}/"
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        parser = _PMLRParser()
        parser.feed(html)

        papers = []
        for rec in parser.papers:
            p = self._record_to_paper(rec, venue, rank, year, volume)
            if p:
                papers.append(p)
        return papers

    @staticmethod
    def _record_to_paper(
        rec: dict[str, Any],
        venue: str,
        rank: str,
        year: int,
        volume: str,
    ) -> Paper | None:
        title = rec.get("title", "").strip()
        if not title:
            return None

        paper_url = rec.get("url", "")
        # Build a stable ID from the URL slug or title hash
        slug = paper_url.rstrip("/").split("/")[-1] if paper_url else ""
        paper_id = f"pmlr:v{volume}:{slug}" if slug else f"pmlr:v{volume}:{re.sub(r'[^a-z0-9]', '', title.lower())[:30]}"

        abstract = rec.get("abstract", "").strip()
        authors  = rec.get("authors", [])

        return Paper(
            id=paper_id,
            source="pmlr",
            source_type="conference",
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            published_date=f"{year}-01-01",
            venue=venue,
            conference_rank=rank,
            paper_url=paper_url,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
