"""
CVF Open Access connector.

Fetches papers from openaccess.thecvf.com — no API key required.
Covers CVPR, ICCV, ECCV.

Note: CVF listing pages include titles and authors but not abstracts.
Abstracts are on individual paper pages; we fetch them for the first
MAX_ABSTRACT_FETCH papers (sorted by listing order) to stay reasonable.
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

_BASE = "https://openaccess.thecvf.com"
_MAX_ABSTRACT_FETCH = 200   # fetch individual pages for top N papers
_DELAY = 1.5

# conference key → (url_path, venue name, rank, year)
_CONFERENCES: dict[str, tuple[str, str, str, int]] = {
    "CVPR2024": ("CVPR2024?day=all",  "CVPR", "A*", 2024),
    "CVPR2023": ("CVPR2023?day=all",  "CVPR", "A*", 2023),
    "ICCV2023": ("ICCV2023?day=all",  "ICCV", "A*", 2023),
    "ECCV2024": ("ECCV2024?day=all",  "ECCV", "A*", 2024),
    "ECCV2022": ("ECCV2022?day=all",  "ECCV", "A*", 2022),
}


class _CVFListParser(HTMLParser):
    """Parse the CVF all-papers listing page.

    CVF HTML structure (simplified):
        <dt class="ptitle"><a href="/...paper-page...">Title</a></dt>
        <dd>
          <form>
            <input name="paper_src" value="path/to.pdf">
            <input name="abs_src"   value="path/to-abstract.html">
          </form>
          <div class="abstract hide">Abstract text...</div>
          Authors: Author1, Author2, ...
        </dd>
    """

    def __init__(self) -> None:
        super().__init__()
        self.papers: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._in_ptitle = False
        self._in_authors_dd = False
        self._in_abstract = False
        self._dd_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "")

        if tag == "dt" and "ptitle" in cls:
            self._current = {"title": "", "url": "", "pdf_url": "", "abstract": "", "authors_text": ""}
            self._in_ptitle = True

        elif tag == "a" and self._in_ptitle and self._current:
            href = attr_dict.get("href", "")
            if href:
                self._current["url"] = href if href.startswith("http") else f"{_BASE}{href}"

        elif tag == "dd" and self._current is not None:
            self._in_authors_dd = True
            self._dd_depth += 1

        elif tag == "input" and self._current is not None:
            name = attr_dict.get("name", "")
            val  = attr_dict.get("value", "")
            if name == "paper_src" and val:
                self._current["pdf_url"] = f"{_BASE}/{val}" if not val.startswith("http") else val

        elif tag == "div" and "abstract" in cls and self._current is not None:
            self._in_abstract = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "dt":
            self._in_ptitle = False
        elif tag == "div" and self._in_abstract:
            self._in_abstract = False
        elif tag == "dd" and self._in_authors_dd:
            self._dd_depth -= 1
            if self._dd_depth <= 0:
                self._in_authors_dd = False
                if self._current and self._current.get("title"):
                    # Parse authors from accumulated text
                    raw = self._current.get("authors_text", "")
                    self._current["authors"] = _parse_authors(raw)
                    self.papers.append(self._current)
                    self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        text = data.strip()
        if not text:
            return
        if self._in_ptitle:
            self._current["title"] += text
        elif self._in_abstract:
            self._current["abstract"] += " " + text
        elif self._in_authors_dd:
            self._current["authors_text"] += " " + text


def _parse_authors(raw: str) -> list[str]:
    """Extract author names from CVF author string."""
    # Remove common noise
    raw = re.sub(r'\s+', ' ', raw).strip()
    raw = raw.lstrip("·").strip()
    # Authors are separated by · or comma
    if "·" in raw:
        return [a.strip() for a in raw.split("·") if a.strip()]
    return [a.strip() for a in raw.split(",") if a.strip() and len(a.strip()) > 1]


class CVFConnector(BaseConnector):
    """Fetches papers from CVF Open Access (CVPR, ICCV, ECCV)."""

    def __init__(self, conferences: list[str] | None = None) -> None:
        self._conferences = conferences or list(_CONFERENCES.keys())

    @property
    def source_name(self) -> str:
        return "cvf"

    def fetch_all(self) -> list[Paper]:
        """Fetch ALL papers from configured CVF conferences."""
        all_papers: list[Paper] = []
        seen: set[str] = set()
        for conf_key in self._conferences:
            if conf_key not in _CONFERENCES:
                log.warning("[cvf] unknown conference key: %s", conf_key)
                continue
            path, venue, rank, year = _CONFERENCES[conf_key]
            try:
                papers = self._fetch_conference(path, venue, rank, year)
                log.info("[cvf] %s → %d papers", conf_key, len(papers))
                for p in papers:
                    if p.id not in seen:
                        seen.add(p.id)
                        all_papers.append(p)
            except Exception as exc:
                log.warning("[cvf] %s failed: %s", conf_key, exc)
            time.sleep(_DELAY)
        return all_papers

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        q = query.lower()
        results: list[Paper] = []
        for conf_key in self._conferences:
            if conf_key not in _CONFERENCES:
                continue
            path, venue, rank, year = _CONFERENCES[conf_key]
            try:
                papers = self._fetch_conference(path, venue, rank, year)
                matched = [
                    p for p in papers
                    if q in p.title.lower() or q in (p.abstract or "").lower()
                ]
                results.extend(matched[:max_results])
            except Exception as exc:
                log.warning("[cvf] %s query failed: %s", conf_key, exc)
            if len(results) >= max_results:
                break
        return results[:max_results]

    # ── internals ─────────────────────────────────────────────────────────────

    def _fetch_conference(self, path: str, venue: str, rank: str, year: int) -> list[Paper]:
        url = f"{_BASE}/{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        parser = _CVFListParser()
        parser.feed(html)
        log.debug("[cvf] parsed %d records from %s", len(parser.papers), path)

        papers = []
        for i, rec in enumerate(parser.papers):
            p = self._record_to_paper(rec, venue, rank, year)
            if p:
                papers.append(p)

        # Fetch abstracts for the first N papers that don't have one yet
        missing = [p for p in papers if not p.abstract][:_MAX_ABSTRACT_FETCH]
        if missing:
            log.info("[cvf] fetching abstracts for %d papers …", len(missing))
            self._enrich_abstracts(missing)

        return papers

    @staticmethod
    def _enrich_abstracts(papers: list[Paper]) -> None:
        """Fetch individual paper pages to get abstracts."""
        for p in papers:
            if not p.paper_url:
                continue
            try:
                req = urllib.request.Request(
                    p.paper_url,
                    headers={"User-Agent": "ResearchScope/1.0"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    html = resp.read().decode("utf-8", errors="replace")
                # Extract abstract: <div id="abstract">...</div>
                m = re.search(r'<div[^>]+id=["\']abstract["\'][^>]*>(.*?)</div>', html, re.S)
                if m:
                    p.abstract = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            except Exception:
                pass
            time.sleep(0.5)

    @staticmethod
    def _record_to_paper(rec: dict[str, Any], venue: str, rank: str, year: int) -> Paper | None:
        title = rec.get("title", "").strip()
        if not title:
            return None

        paper_url = rec.get("url", "")
        slug = paper_url.rstrip("/").split("/")[-1] if paper_url else ""
        paper_id = f"cvf:{slug}" if slug else f"cvf:{re.sub(r'[^a-z0-9]', '', title.lower())[:40]}"

        return Paper(
            id=paper_id,
            source="cvf",
            source_type="conference",
            title=title,
            abstract=rec.get("abstract", "").strip(),
            authors=rec.get("authors", []),
            year=year,
            published_date=f"{year}-01-01",
            venue=venue,
            conference_rank=rank,
            paper_url=paper_url,
            pdf_url=rec.get("pdf_url", ""),
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
