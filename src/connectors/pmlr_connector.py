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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

_BASE = "https://proceedings.mlr.press"

# volume → (venue name, rank, year)
_VOLUMES: dict[str, tuple[str, str, int]] = {
    # ICML
    "306": ("ICML",    "A*", 2026),
    "267": ("ICML",    "A*", 2025),
    "235": ("ICML",    "A*", 2024),
    "202": ("ICML",    "A*", 2023),
    "162": ("ICML",    "A*", 2022),
    "139": ("ICML",    "A*", 2021),
    "119": ("ICML",    "A*", 2020),
    # AISTATS
    "300": ("AISTATS", "A",  2026),
    "258": ("AISTATS", "A",  2025),
    "238": ("AISTATS", "A",  2024),
    "206": ("AISTATS", "A",  2023),
    "151": ("AISTATS", "A",  2022),
    "130": ("AISTATS", "A",  2021),
    # UAI
    "337": ("UAI",     "A",  2026),
    "286": ("UAI",     "A",  2025),
    "244": ("UAI",     "A",  2024),
    "216": ("UAI",     "A",  2023),
    "180": ("UAI",     "A",  2022),
    "161": ("UAI",     "A",  2021),
}

_DELAY = 2.0
_ABSTRACT_WORKERS = 16
_ABSTRACT_TIMEOUT = 15


class _PMLRParser(HTMLParser):
    """Extract paper records from a PMLR proceedings index page.

    Current markup (2025+):
        <div class="paper">
          <p class="title">Title</p>
          <p class="details"><span class="authors">A,&nbsp;B</span>; ...</p>
          <p class="links">[<a href=".../x.html">abs</a>][<a href="...pdf">Download PDF</a>]</p>
        </div>
    Older volumes put the link on the title and the authors in <p class="authors">;
    both layouts are handled.
    """

    def __init__(self) -> None:
        super().__init__()
        self.papers: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._in_title = False
        self._in_authors = False
        self._in_abstract = False
        self._link: str | None = None   # href of the <a> being read in p.links
        self._link_text = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "") or ""

        if tag == "div" and cls == "paper":
            self._current = {"title": "", "authors": [], "abstract": "", "url": "", "pdf_url": ""}
        elif self._current is not None:
            if tag == "p" and cls == "title":
                self._in_title = True
            elif tag in ("p", "span") and cls == "authors":
                self._in_authors = True
                self._current["authors_text"] = ""
            elif tag == "p" and cls == "abstract":
                self._in_abstract = True
            elif tag == "a":
                href = attr_dict.get("href", "")
                href = href if href.startswith("http") else f"{_BASE}{href}" if href else ""
                if self._in_title and href:
                    self._current["url"] = href
                else:
                    self._link, self._link_text = href, ""

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag == "a" and self._link is not None:
            label = self._link_text.strip().lower()
            if label == "abs" and not self._current["url"]:
                self._current["url"] = self._link
            elif "pdf" in label and not self._current["pdf_url"]:
                self._current["pdf_url"] = self._link
            self._link = None
        if tag in ("p", "span") and self._in_authors:
            text = self._current.pop("authors_text", "").replace("\xa0", " ")
            self._current["authors"] = [a.strip() for a in text.split(",") if a.strip()]
            self._in_authors = False
        if tag == "p":
            self._in_title = False
            self._in_abstract = False
        if tag == "div":
            if self._current.get("title"):
                self.papers.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        if self._link is not None:
            self._link_text += data
        if self._in_authors:
            self._current["authors_text"] += data
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self._current["title"] += text
        elif self._in_abstract:
            self._current["abstract"] += " " + text


class PMLRConnector(BaseConnector):
    """Fetches ALL papers from PMLR proceedings (ICML and similar venues)."""

    def __init__(self, volumes: dict[str, tuple[str, str, int]] | None = None) -> None:
        self._volumes = volumes or _VOLUMES

    @property
    def source_name(self) -> str:
        return "pmlr"

    def fetch_all(self, skip_keys: set[str] | None = None) -> list[Paper]:
        """Fetch ALL papers from every configured PMLR volume.

        ``skip_keys`` holds "<venue>:<year>" blocks already archived (settled
        past years); those volumes are skipped to avoid re-downloading them.
        """
        skip_keys = skip_keys or set()
        all_papers: list[Paper] = []
        seen: set[str] = set()
        for vol, (venue, rank, year) in self._volumes.items():
            if f"{venue}:{year}" in skip_keys:
                log.info("[pmlr] v%s (%s %d) archived — skipping", vol, venue, year)
                continue
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

        # Volume listings carry no abstracts; each paper page does
        missing = [p for p in papers if not p.abstract]
        if missing:
            log.info("[pmlr] fetching abstracts for %d papers …", len(missing))
            self._enrich_abstracts(missing)
        return papers

    @staticmethod
    def _enrich_abstracts(papers: list[Paper]) -> None:
        """Fetch each paper's PMLR page for its abstract (concurrent)."""
        def fetch_one(p: Paper) -> tuple[Paper, str]:
            if not p.paper_url.startswith("http"):
                return p, ""
            try:
                req = urllib.request.Request(p.paper_url, headers={"User-Agent": "ResearchScope/1.0"})
                with urllib.request.urlopen(req, timeout=_ABSTRACT_TIMEOUT) as resp:
                    page = resp.read().decode("utf-8", errors="replace")
                m = re.search(r'<div[^>]+id=["\']abstract["\'][^>]*>(.*?)</div>', page, re.S)
                return p, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else ""
            except Exception:
                return p, ""

        with ThreadPoolExecutor(max_workers=_ABSTRACT_WORKERS) as pool:
            for fut in as_completed([pool.submit(fetch_one, p) for p in papers]):
                paper, abstract = fut.result()
                if abstract:
                    paper.abstract = abstract

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
            pdf_url=rec.get("pdf_url", ""),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
