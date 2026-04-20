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
# Only cs.* categories — these are CoRR (Computing Research Repository) papers.
# stat.ML / eess.* are intentionally excluded: they live outside CoRR and many
# stat.ML papers also appear under cs.LG, so there is minimal loss.
CATEGORY_TAG_MAP: dict[str, str] = {
    "cs.AI":  "Artificial Intelligence",
    "cs.CL":  "NLP",
    "cs.CV":  "Computer Vision",
    "cs.LG":  "Machine Learning",
    "cs.NE":  "Neural Networks",
    "cs.RO":  "Robotics",
    "cs.IR":  "Information Retrieval",
    "cs.SE":  "Software Engineering",
    "cs.DB":  "Databases",
    "cs.CR":  "Cryptography & Security",
    "cs.HC":  "Human-Computer Interaction",
    "cs.MA":  "Multi-Agent Systems",
    "cs.GR":  "Computer Graphics",
    "cs.MM":  "Multimedia",
    "cs.SY":  "Systems & Control",
    "cs.DC":  "Distributed Computing",
    "cs.PL":  "Programming Languages",
    "cs.GT":  "Game Theory",
    "cs.DS":  "Data Structures & Algorithms",
}

_ARXIV_NS  = "http://www.w3.org/2005/Atom"
_API_BASE  = "https://export.arxiv.org/api/query"
_OAI_BASE  = "https://export.arxiv.org/oai2"
_OAI_NS    = "http://www.openarchives.org/OAI/2.0/"
_OAI_ARXIV = "http://arxiv.org/OAI/arXiv/"
# OAI-PMH requires at least 20 seconds between paginated requests (arXiv ToS).
_OAI_PAGE_DELAY = 20.0

# CoRR (cs.*) categories fetched on every daily run.
# All entries start with "cs." — this is what defines a CoRR paper.
_DEFAULT_CATEGORIES = [
    "cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.NE",
    "cs.IR", "cs.MA", "cs.RO", "cs.SE", "cs.HC",
    "cs.CR", "cs.DB", "cs.GR", "cs.MM", "cs.SY",
    "cs.DC", "cs.PL", "cs.GT", "cs.DS",
]


def _ns(name: str) -> str:
    return f"{{{_ARXIV_NS}}}{name}"


def _is_corr_categories(categories: list[str]) -> bool:
    """Return True only if the category list contains at least one cs.* category (CoRR)."""
    return any(c.startswith("cs.") for c in categories)


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
        batch_size: int = 300,
        delay_seconds: float = 3.0,
    ) -> list[Paper]:
        """Fetch ALL papers submitted between *date_from* and *date_to* (inclusive).

        Strategy:
          1. OAI-PMH (set=cs) — the correct bulk-harvest interface; supports exact
             date ranges and returns every CoRR submission without relying on the
             search API's unsupported submittedDate field.
          2. Atom API fallback — category-filtered search with pagination.
        """
        dt_to = date_to or date.today()
        cats  = categories or _DEFAULT_CATEGORIES

        log.info(
            "fetch_range: %s → %s  categories=%d  max=%d",
            date_from, dt_to, len(cats), max_results,
        )

        # ── 1. OAI-PMH — designed for exactly this use case ───────────────────
        try:
            papers = self._fetch_via_oai(date_from, dt_to, max_results=max_results)
            if papers:
                log.info("fetch_range complete via OAI-PMH: %d papers", len(papers))
                return papers
            log.warning("OAI-PMH returned 0 papers — falling back to Atom API")
        except Exception as exc:
            log.warning("OAI-PMH fetch failed: %s — falling back to Atom API", exc)

        # ── 2. Atom API fallback with pagination ──────────────────────────────
        import time

        cat_filter = " OR ".join(f"cat:{c}" for c in cats)
        from_str   = date_from.strftime("%Y%m%d") + "000000"
        to_str     = dt_to.strftime("%Y%m%d") + "235959"
        query      = f"({cat_filter}) AND submittedDate:[{from_str} TO {to_str}]"

        all_papers: list[Paper] = []
        seen_ids:   set[str]   = set()
        start = 0
        _delays = [delay_seconds * 2, delay_seconds * 4, delay_seconds * 8]

        while start < max_results:
            this_batch = min(batch_size, max_results - start)
            batch: list[Paper] = []
            last_exc: Exception | None = None

            for attempt, wait in enumerate([0.0] + _delays):
                if wait:
                    log.warning("fetch_range batch start=%d attempt %d — waiting %.0fs", start, attempt, wait)
                    time.sleep(wait)
                try:
                    batch = self._fetch_via_api_paginated(query, start, this_batch)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    log.warning("fetch_range batch start=%d attempt %d failed: %s", start, attempt, exc)

            if last_exc is not None:
                log.error("fetch_range batch start=%d failed after all retries — stopping", start)
                break

            new = 0
            for p in batch:
                if p.id not in seen_ids:
                    seen_ids.add(p.id)
                    all_papers.append(p)
                    new += 1

            log.info("  batch start=%d fetched=%d new=%d total=%d", start, len(batch), new, len(all_papers))

            if len(batch) < this_batch:
                break   # reached last page

            start += this_batch
            time.sleep(delay_seconds)

        log.info("fetch_range complete via Atom API: %d papers", len(all_papers))
        return all_papers

    # ── OAI-PMH bulk harvester ────────────────────────────────────────────────

    def _fetch_via_oai(
        self,
        date_from: date,
        date_to: date,
        max_results: int = 30_000,
    ) -> list[Paper]:
        """Harvest all CoRR (cs.*) papers via arXiv OAI-PMH.

        Uses set=cs which maps exactly to the Computing Research Repository.
        Paginates via resumption tokens; respects arXiv's required 20-second
        inter-page delay.
        """
        import time

        all_papers: list[Paper] = []
        seen_ids:   set[str]   = set()

        params = urllib.parse.urlencode({
            "verb":           "ListRecords",
            "from":           date_from.isoformat(),
            "until":          date_to.isoformat(),
            "metadataPrefix": "arXiv",
            "set":            "cs",
        })
        url: str | None = f"{_OAI_BASE}?{params}"
        page = 0

        while url and len(all_papers) < max_results:
            page += 1
            if page > 1:
                time.sleep(_OAI_PAGE_DELAY)

            req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
                data = resp.read()

            root = ET.fromstring(data)

            error_el = root.find(f"{{{_OAI_NS}}}error")
            if error_el is not None:
                raise RuntimeError(f"OAI-PMH error ({error_el.get('code')}): {error_el.text}")

            list_records = root.find(f"{{{_OAI_NS}}}ListRecords")
            if list_records is None:
                break

            for record in list_records.findall(f"{{{_OAI_NS}}}record"):
                paper = self._oai_record_to_paper(record)
                if paper and paper.id not in seen_ids:
                    seen_ids.add(paper.id)
                    all_papers.append(paper)

            token_el = list_records.find(f"{{{_OAI_NS}}}resumptionToken")
            if token_el is not None and token_el.text and token_el.text.strip():
                token  = token_el.text.strip()
                params = urllib.parse.urlencode({"verb": "ListRecords", "resumptionToken": token})
                url    = f"{_OAI_BASE}?{params}"
                log.info("  OAI-PMH page %d: %d papers so far, resuming…", page, len(all_papers))
            else:
                url = None

        return all_papers

    def _oai_record_to_paper(self, record: ET.Element) -> Paper | None:
        header = record.find(f"{{{_OAI_NS}}}header")
        if header is not None and header.get("status") == "deleted":
            return None

        metadata = record.find(f"{{{_OAI_NS}}}metadata")
        if metadata is None:
            return None

        arxiv_el = metadata.find(f"{{{_OAI_ARXIV}}}arXiv")
        if arxiv_el is None:
            return None

        def oai_text(tag: str) -> str:
            el = arxiv_el.find(f"{{{_OAI_ARXIV}}}{tag}")
            return (el.text or "").strip() if el is not None else ""

        arxiv_id = oai_text("id")
        if not arxiv_id:
            return None

        categories = [c.strip() for c in oai_text("categories").split() if c.strip()]
        if not _is_corr_categories(categories):
            return None
        tags = list({CATEGORY_TAG_MAP[c] for c in categories if c in CATEGORY_TAG_MAP})

        authors_el = arxiv_el.find(f"{{{_OAI_ARXIV}}}authors")
        authors: list[str] = []
        if authors_el is not None:
            for author_el in authors_el.findall(f"{{{_OAI_ARXIV}}}author"):
                keyname   = author_el.find(f"{{{_OAI_ARXIV}}}keyname")
                forenames = author_el.find(f"{{{_OAI_ARXIV}}}forenames")
                parts = []
                if forenames is not None and forenames.text:
                    parts.append(forenames.text.strip())
                if keyname is not None and keyname.text:
                    parts.append(keyname.text.strip())
                if parts:
                    authors.append(" ".join(parts))

        created_str = oai_text("created")
        year, published_date = 0, ""
        if created_str:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", created_str)
            if m:
                year = int(m.group(1))
                published_date = created_str[:10]

        return Paper(
            id=f"arxiv:{arxiv_id}",
            source=self.source_name,
            source_type="preprint",
            title=oai_text("title").replace("\n", " ").strip(),
            abstract=oai_text("abstract").replace("\n", " ").strip(),
            authors=authors,
            year=year,
            published_date=published_date,
            venue="arXiv",
            paper_url=f"https://arxiv.org/abs/{arxiv_id}",
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
            tags=tags,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Primary: arxiv package ────────────────────────────────────────────────

    def _fetch_via_package(self, query: str, max_results: int) -> list[Paper]:
        import arxiv  # type: ignore

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        return [p for r in client.results(search) if (p := self._result_to_paper(r)) is not None]

    def _result_to_paper(self, result: object) -> Paper | None:
        entry_id: str = getattr(result, "entry_id", "") or ""
        arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id

        categories: list[str] = list(getattr(result, "categories", []) or [])
        if not _is_corr_categories(categories):
            return None   # skip non-CoRR papers (physics, math, bio, etc.)
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
        return [p for e in root.findall(_ns("entry")) if (p := self._entry_to_paper(e)) is not None]

    def _entry_to_paper(self, entry: ET.Element) -> Paper | None:
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
        if not _is_corr_categories(categories):
            return None   # skip non-CoRR papers (physics, math, bio, etc.)
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
