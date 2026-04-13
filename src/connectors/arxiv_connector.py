"""
ArXiv connector.

Uses the `arxiv` package when available; falls back to the public Atom API.
"""
from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

# arXiv category → human-readable tag
CATEGORY_TAG_MAP: dict[str, str] = {
    "cs.AI":   "Artificial Intelligence",
    "cs.CL":   "NLP",
    "cs.CV":   "Computer Vision",
    "cs.LG":   "Machine Learning",
    "cs.NE":   "Neural Networks",
    "cs.RO":   "Robotics",
    "cs.IR":   "Information Retrieval",
    "cs.SE":   "Software Engineering",
    "cs.DB":   "Databases",
    "cs.CR":   "Cryptography & Security",
    "cs.HC":   "Human-Computer Interaction",
    "cs.MA":   "Multi-Agent Systems",
    "stat.ML": "Machine Learning",
    "math.OC": "Optimization",
    "eess.AS": "Speech",
    "eess.IV": "Computer Vision",
}

_ARXIV_NS = "http://www.w3.org/2005/Atom"
_API_BASE  = "https://export.arxiv.org/api/query"

# CS + ML categories to sweep when fetching by date
_DEFAULT_CATEGORIES = [
    "cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.NE",
    "cs.IR", "cs.MA", "cs.RO", "cs.SE", "cs.HC",
    "cs.CR", "cs.DB", "stat.ML", "eess.AS", "eess.IV",
]


def _ns(name: str) -> str:
    return f"{{{_ARXIV_NS}}}{name}"


class ArxivConnector(BaseConnector):
    """Fetches papers from arXiv."""

    @property
    def source_name(self) -> str:
        return "arxiv"

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        try:
            return self._fetch_via_package(query, max_results)
        except ImportError:
            log.debug("arxiv package not installed — using Atom API fallback")
        except Exception as exc:
            log.debug("arxiv package fetch failed: %s — falling back", exc)
        try:
            return self._fetch_via_api(query, max_results)
        except Exception as exc:
            log.warning("arXiv Atom API fetch failed: %s", exc)
            return []

    def fetch_today(
        self,
        categories: list[str] | None = None,
        max_results: int = 2000,
        lookback_days: int = 2,
    ) -> list[Paper]:
        """Fetch all papers submitted in the last *lookback_days* across CS/ML categories."""
        today     = date.today()
        date_from = today - timedelta(days=lookback_days)
        return self.fetch_range(date_from, today, categories=categories, max_results=max_results)

    def fetch_range(
        self,
        date_from: date,
        date_to: date | None = None,
        categories: list[str] | None = None,
        max_results: int = 30_000,
        batch_size: int = 500,
        delay_seconds: float = 3.0,
    ) -> list[Paper]:
        """Fetch ALL papers submitted between *date_from* and *date_to* (inclusive).

        Paginates automatically.  Respects arXiv's recommended 3-second delay
        between requests.  At ~300 papers/day a 3-month backfill takes ~3 min.
        """
        import time

        cats = categories or _DEFAULT_CATEGORIES
        cat_filter = " OR ".join(f"cat:{c}" for c in cats)

        dt_to   = date_to or date.today()
        from_str = date_from.strftime("%Y%m%d") + "000000"
        to_str   = dt_to.strftime("%Y%m%d") + "235959"

        query = f"({cat_filter}) AND submittedDate:[{from_str} TO {to_str}]"
        log.info(
            "fetch_range: %s → %s  categories=%d  max=%d",
            date_from, dt_to, len(cats), max_results,
        )

        all_papers: list[Paper] = []
        seen_ids:   set[str]   = set()
        start = 0

        while start < max_results:
            this_batch = min(batch_size, max_results - start)
            try:
                papers = self._fetch_via_api_paginated(query, start, this_batch)
            except Exception as exc:
                log.warning("fetch_range batch start=%d failed: %s — retrying once", start, exc)
                time.sleep(delay_seconds * 2)
                try:
                    papers = self._fetch_via_api_paginated(query, start, this_batch)
                except Exception as exc2:
                    log.error("fetch_range batch start=%d failed again: %s", start, exc2)
                    break

            new = 0
            for p in papers:
                if p.id not in seen_ids:
                    seen_ids.add(p.id)
                    all_papers.append(p)
                    new += 1

            log.info(
                "  batch start=%d fetched=%d new=%d total=%d",
                start, len(papers), new, len(all_papers),
            )

            if len(papers) < this_batch:
                break   # reached last page

            start += this_batch
            time.sleep(delay_seconds)   # be polite to arXiv

        log.info("fetch_range complete: %d papers", len(all_papers))
        return all_papers

    # ── Primary: arxiv package ────────────────────────────────────────────────

    def _fetch_via_package(self, query: str, max_results: int) -> list[Paper]:
        import arxiv  # type: ignore

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        return [self._result_to_paper(r) for r in client.results(search)]

    def _result_to_paper(self, result: object) -> Paper:
        entry_id: str = getattr(result, "entry_id", "") or ""
        arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id

        categories: list[str] = list(getattr(result, "categories", []) or [])
        tags = list({CATEGORY_TAG_MAP[c] for c in categories if c in CATEGORY_TAG_MAP})

        published = getattr(result, "published", None)
        year = published.year if published else 0
        published_date = published.strftime("%Y-%m-%d") if published else ""

        authors_raw = getattr(result, "authors", []) or []
        authors = [str(a) for a in authors_raw]

        return Paper(
            id=f"arxiv:{arxiv_id}",
            source=self.source_name,
            source_type="preprint",
            title=(getattr(result, "title", "") or "").replace("\n", " ").strip(),
            abstract=(getattr(result, "summary", "") or "").replace("\n", " ").strip(),
            authors=authors,
            year=year,
            published_date=published_date,
            venue="arXiv",
            paper_url=entry_id,
            pdf_url=getattr(result, "pdf_url", "") or "",
            tags=tags,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Fallback: Atom API ────────────────────────────────────────────────────

    def _fetch_via_api(self, query: str, max_results: int) -> list[Paper]:
        return self._fetch_via_api_paginated(f"all:{query}", 0, max_results)

    def _fetch_via_api_paginated(self, search_query: str, start: int, max_results: int) -> list[Paper]:
        params = urllib.parse.urlencode({
            "search_query": search_query,
            "start": start,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        })
        url = f"{_API_BASE}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            data = resp.read()
        root = ET.fromstring(data)
        return [self._entry_to_paper(e) for e in root.findall(_ns("entry"))]

    def _entry_to_paper(self, entry: ET.Element) -> Paper:
        def text(tag: str) -> str:
            el = entry.find(_ns(tag))
            return (el.text or "").strip() if el is not None else ""

        entry_id = text("id")
        arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id

        authors = [
            (a.find(_ns("name")).text or "").strip()
            for a in entry.findall(_ns("author"))
            if a.find(_ns("name")) is not None
        ]

        categories: list[str] = []
        for el in entry.findall("{http://arxiv.org/schemas/atom}primary_category"):
            categories.append(el.get("term", ""))
        for el in entry.findall(_ns("category")):
            term = el.get("term", "")
            if term:
                categories.append(term)
        tags = list({CATEGORY_TAG_MAP[c] for c in categories if c in CATEGORY_TAG_MAP})

        published_str = text("published")
        year = 0
        published_date = ""
        if published_str:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", published_str)
            if m:
                year = int(m.group(1))
                published_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        pdf_url = ""
        for link in entry.findall(_ns("link")):
            if link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")

        return Paper(
            id=f"arxiv:{arxiv_id}",
            source=self.source_name,
            source_type="preprint",
            title=text("title").replace("\n", " "),
            abstract=text("summary").replace("\n", " "),
            authors=authors,
            year=year,
            published_date=published_date,
            venue="arXiv",
            paper_url=entry_id,
            pdf_url=pdf_url,
            tags=tags,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
