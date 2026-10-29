"""
Conference "virtual site" connector (neurips.cc, icml.cc, iclr.cc).

These sites publish every accepted paper as one public JSON file
(``/static/virtual/data/<conf>-<year>-orals-posters.json``) with titles,
authors, the accept decision and the OpenReview link. No login is needed,
which matters because api2.openreview.net now answers anonymous and CI
requests with a challenge (HTTP 403).

The JSON has no abstracts, so each paper's poster page is fetched for one.
"""
from __future__ import annotations

import html
import json
import logging
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

_ABSTRACT_WORKERS = 16
_ABSTRACT_TIMEOUT = 15
_DELAY = 1.0

# key → (site, data-file prefix, venue name, rank, year)
# Add each new edition here once its accepted-paper list is published.
_CONFERENCES: dict[str, tuple[str, str, str, str, int]] = {
    "NeurIPS2026": ("https://neurips.cc", "neurips-2026", "NeurIPS", "A*", 2026),
    "NeurIPS2025": ("https://neurips.cc", "neurips-2025", "NeurIPS", "A*", 2025),
}

_ABSTRACT_RE = re.compile(r'<div[^>]*class="[^"]*\babstract\b[^"]*"[^>]*>(.*?)</div>', re.S)


def _parse_tier(decision: str, eventtype: str) -> str:
    """'Accept (spotlight)' → 'spotlight'; falls back to the event type."""
    low = f"{decision} {eventtype}".lower()
    for tier in ("oral", "spotlight", "poster"):
        if tier in low:
            return tier
    return ""


def _clean_abstract(fragment: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^Abstract:?\s*", "", text)


class MiniconfConnector(BaseConnector):
    """Fetches ALL accepted papers from conference virtual sites."""

    def __init__(self, conferences: list[str] | None = None) -> None:
        self._conferences = conferences or list(_CONFERENCES.keys())

    @property
    def source_name(self) -> str:
        return "miniconf"

    def fetch_all(self, skip_keys: set[str] | None = None) -> list[Paper]:
        """Fetch every accepted paper for the configured editions.

        ``skip_keys`` holds "<venue>:<year>" blocks already archived.
        """
        skip_keys = skip_keys or set()
        all_papers: list[Paper] = []
        for key in self._conferences:
            if key not in _CONFERENCES:
                log.warning("[miniconf] unknown conference key: %s", key)
                continue
            site, prefix, venue, rank, year = _CONFERENCES[key]
            if f"{venue}:{year}" in skip_keys:
                log.info("[miniconf] %s archived — skipping", key)
                continue
            try:
                papers = self._fetch_conference(site, prefix, venue, rank, year)
                log.info("[miniconf] %s → %d papers", key, len(papers))
                all_papers.extend(papers)
            except Exception as exc:
                log.warning("[miniconf] %s failed: %s", key, exc)
            time.sleep(_DELAY)
        return all_papers

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        q = query.lower()
        out: list[Paper] = []
        for paper in self.fetch_all():
            if q in paper.title.lower() or q in paper.abstract.lower():
                out.append(paper)
                if len(out) >= max_results:
                    break
        return out

    # ── internals ─────────────────────────────────────────────────────────────

    def _fetch_conference(self, site: str, prefix: str, venue: str, rank: str,
                          year: int) -> list[Paper]:
        url = f"{site}/static/virtual/data/{prefix}-orals-posters.json"
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        records = data.get("results", data) if isinstance(data, dict) else data
        papers = self.records_to_papers(records, site, venue, rank, year)
        missing = [p for p in papers if not p.abstract]
        if missing:
            log.info("[miniconf] fetching abstracts for %d papers …", len(missing))
            self._enrich_abstracts(missing)
        return papers

    @classmethod
    def records_to_papers(cls, records: list[dict[str, Any]], site: str, venue: str,
                          rank: str, year: int) -> list[Paper]:
        """Map JSON records to Papers, one per paper.

        Orals are listed twice (an Oral event plus its Poster), so records are
        merged by title and the strongest tier wins.
        """
        order = {"oral": 3, "spotlight": 2, "poster": 1, "": 0}
        by_title: dict[str, Paper] = {}
        for rec in records:
            paper = cls._record_to_paper(rec, site, venue, rank, year)
            if not paper:
                continue
            key = re.sub(r"[^a-z0-9]", "", paper.title.lower())
            kept = by_title.get(key)
            if kept is None:
                by_title[key] = paper
                continue
            if order[paper.presentation_type] > order[kept.presentation_type]:
                kept.presentation_type = paper.presentation_type
            # a Poster event links its own page, which carries the abstract
            if "/poster/" in paper.paper_url and "/poster/" not in kept.paper_url:
                kept.paper_url = paper.paper_url
        return list(by_title.values())

    @staticmethod
    def _record_to_paper(rec: dict[str, Any], site: str, venue: str, rank: str,
                         year: int) -> Paper | None:
        title = (rec.get("name") or "").strip()
        decision = rec.get("decision") or ""
        if not title or (decision and not decision.lower().startswith("accept")):
            return None
        authors = [a.get("fullname", "").strip() for a in rec.get("authors") or []
                   if isinstance(a, dict) and a.get("fullname")]
        page = rec.get("virtualsite_url") or ""
        openreview = rec.get("paper_url") or ""
        uid = rec.get("uid") or rec.get("id") or re.sub(r"[^a-z0-9]", "", title.lower())[:40]
        return Paper(
            id=f"miniconf:{venue.lower()}{year}:{uid}",
            source="miniconf",
            source_type="conference",
            title=title,
            abstract=(rec.get("abstract") or "").strip(),
            authors=authors,
            year=year,
            published_date=f"{year}-01-01",
            venue=venue,
            conference_rank=rank,
            presentation_type=_parse_tier(decision, rec.get("eventtype") or ""),
            paper_url=f"{site}{page}" if page.startswith("/") else (openreview or page),
            pdf_url=openreview.replace("/forum?", "/pdf?") if "openreview.net/forum" in openreview else "",
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _enrich_abstracts(papers: list[Paper]) -> None:
        """Fetch each paper's virtual-site page for its abstract (concurrent)."""
        def fetch_one(p: Paper) -> tuple[Paper, str]:
            if not p.paper_url.startswith("http"):
                return p, ""
            try:
                req = urllib.request.Request(p.paper_url, headers={"User-Agent": "ResearchScope/1.0"})
                with urllib.request.urlopen(req, timeout=_ABSTRACT_TIMEOUT) as resp:
                    page = resp.read().decode("utf-8", errors="replace")
                m = _ABSTRACT_RE.search(page)
                return p, _clean_abstract(m.group(1)) if m else ""
            except Exception:
                return p, ""

        with ThreadPoolExecutor(max_workers=_ABSTRACT_WORKERS) as pool:
            for fut in as_completed([pool.submit(fetch_one, p) for p in papers]):
                paper, abstract = fut.result()
                if abstract:
                    paper.abstract = abstract
