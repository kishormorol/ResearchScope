"""ArXiv connector using the arxiv package or the public API as fallback."""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

# ArXiv category → human-readable tag
CATEGORY_TAG_MAP: dict[str, str] = {
    "cs.AI": "Artificial Intelligence",
    "cs.CL": "NLP",
    "cs.CV": "Computer Vision",
    "cs.LG": "Machine Learning",
    "cs.NE": "Neural Networks",
    "cs.RO": "Robotics",
    "cs.IR": "Information Retrieval",
    "cs.SE": "Software Engineering",
    "cs.DB": "Databases",
    "cs.CR": "Cryptography & Security",
    "stat.ML": "Machine Learning",
    "math.OC": "Optimization",
    "eess.AS": "Audio & Speech",
    "eess.IV": "Image & Video",
}

_ARXIV_NS = "http://www.w3.org/2005/Atom"


def _tag(name: str) -> str:
    return f"{{{_ARXIV_NS}}}{name}"


class ArxivConnector(BaseConnector):
    """Fetches papers from arXiv."""

    @property
    def source_name(self) -> str:
        return "arxiv"

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        try:
            return self._fetch_via_package(query, max_results)
        except Exception:
            pass
        try:
            return self._fetch_via_api(query, max_results)
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_via_package(self, query: str, max_results: int) -> list[Paper]:
        import arxiv  # type: ignore

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        papers: list[Paper] = []
        for result in client.results(search):
            papers.append(self._result_to_paper(result))
        return papers

    def _result_to_paper(self, result: object) -> Paper:
        """Convert an arxiv.Result to a Paper."""
        entry_id: str = getattr(result, "entry_id", "") or ""
        arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id

        categories: list[str] = list(getattr(result, "categories", []) or [])
        tags = list({CATEGORY_TAG_MAP[c] for c in categories if c in CATEGORY_TAG_MAP})

        published = getattr(result, "published", None)
        year = published.year if published else 0

        citations = 0
        score = self._compute_score(year, citations)

        return Paper(
            id=f"arxiv:{arxiv_id}",
            title=(getattr(result, "title", "") or "").strip(),
            abstract=(getattr(result, "summary", "") or "").strip(),
            authors=[str(a) for a in (getattr(result, "authors", []) or [])],
            year=year,
            venue="arXiv",
            url=entry_id,
            pdf_url=getattr(result, "pdf_url", "") or "",
            source=self.source_name,
            tags=tags,
            difficulty="intermediate",
            citations=citations,
            read_first_score=score,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # Fallback: public Atom API
    # ------------------------------------------------------------------

    def _fetch_via_api(self, query: str, max_results: int) -> list[Paper]:
        encoded = urllib.parse.quote_plus(query)
        url = (
            f"https://export.arxiv.org/api/query"
            f"?search_query=all:{encoded}&max_results={max_results}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            data = resp.read()
        root = ET.fromstring(data)
        papers: list[Paper] = []
        for entry in root.findall(_tag("entry")):
            papers.append(self._entry_to_paper(entry))
        return papers

    def _entry_to_paper(self, entry: ET.Element) -> Paper:
        def text(tag: str) -> str:
            el = entry.find(_tag(tag))
            return (el.text or "").strip() if el is not None else ""

        entry_id = text("id")
        arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id

        authors = [
            (a.find(_tag("name")).text or "").strip()
            for a in entry.findall(_tag("author"))
            if a.find(_tag("name")) is not None
        ]

        categories = [
            el.get("term", "")
            for el in entry.findall("{http://arxiv.org/schemas/atom}primary_category")
        ]
        # also grab secondary categories
        for el in entry.findall(_tag("category")):
            term = el.get("term", "")
            if term:
                categories.append(term)
        tags = list({CATEGORY_TAG_MAP[c] for c in categories if c in CATEGORY_TAG_MAP})

        published_str = text("published")
        year = 0
        if published_str:
            m = re.match(r"(\d{4})", published_str)
            if m:
                year = int(m.group(1))

        score = self._compute_score(year, 0)
        pdf_url = ""
        for link in entry.findall(_tag("link")):
            if link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")

        return Paper(
            id=f"arxiv:{arxiv_id}",
            title=text("title").replace("\n", " "),
            abstract=text("summary").replace("\n", " "),
            authors=authors,
            year=year,
            venue="arXiv",
            url=entry_id,
            pdf_url=pdf_url,
            source=self.source_name,
            tags=tags,
            difficulty="intermediate",
            citations=0,
            read_first_score=score,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _compute_score(year: int, citations: int) -> float:
        current_year = datetime.now(timezone.utc).year
        recency = max(0, 10 - (current_year - year)) if year else 0
        citation_score = min(citations / 100, 5) if citations else 0
        return round(min(recency * 0.6 + citation_score * 0.4, 10.0), 2)
