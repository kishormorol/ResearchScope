"""ArXiv paper collector."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

import httpx

from researchscope.models.paper import Paper

_ARXIV_API = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivCollector:
    """Fetch papers from the arXiv public API."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def search(
        self,
        query: str,
        max_results: int = 10,
        start: int = 0,
    ) -> list[Paper]:
        """Search arXiv and return a list of :class:`Paper` objects.

        Args:
            query: A query string in arXiv search syntax (e.g. ``"ti:transformer"``).
            max_results: Maximum number of results to return (capped at 100).
            start: Offset for pagination.

        Returns:
            List of matching papers.
        """
        max_results = min(max_results, 100)
        params = {
            "search_query": query,
            "start": start,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        response = httpx.get(_ARXIV_API, params=params, timeout=self._timeout)
        response.raise_for_status()
        return self._parse(response.text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse(self, xml_text: str) -> list[Paper]:
        root = ET.fromstring(xml_text)
        papers: list[Paper] = []
        for entry in root.findall("atom:entry", _NS):
            papers.append(self._entry_to_paper(entry))
        return papers

    def _entry_to_paper(self, entry: ET.Element) -> Paper:
        paper_id = self._text(entry, "atom:id").split("/abs/")[-1]
        title = self._text(entry, "atom:title").replace("\n", " ").strip()
        abstract = self._text(entry, "atom:summary").replace("\n", " ").strip()
        authors = [
            self._text(a, "atom:name")
            for a in entry.findall("atom:author", _NS)
        ]
        published = self._parse_date(self._text(entry, "atom:published"))
        url = f"https://arxiv.org/abs/{paper_id}"
        categories = [
            c.attrib.get("term", "")
            for c in entry.findall("atom:category", _NS)
        ]
        return Paper(
            paper_id=paper_id,
            title=title,
            abstract=abstract,
            authors=authors,
            published=published,
            url=url,
            source="arxiv",
            keywords=categories,
        )

    @staticmethod
    def _text(element: ET.Element, tag: str) -> str:
        child = element.find(tag, _NS)
        return (child.text or "") if child is not None else ""

    @staticmethod
    def _parse_date(raw: str) -> date | None:
        try:
            return date.fromisoformat(raw[:10])
        except (ValueError, TypeError):
            return None
