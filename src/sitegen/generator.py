"""Static site data generator – writes JSON files consumed by the frontend."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from src.normalization.schema import Author, Paper, ResearchGap, Topic


class SiteGenerator:
    """Write JSON data files for the static frontend."""

    def generate(
        self,
        papers: list[Paper],
        authors: list[Author],
        topics: list[Topic],
        gaps: list[ResearchGap],
        output_dir: str = "data",
    ) -> None:
        os.makedirs(output_dir, exist_ok=True)

        self._write(output_dir, "papers.json", [p.to_dict() for p in papers])
        self._write(output_dir, "authors.json", [a.to_dict() for a in authors])
        self._write(output_dir, "topics.json", [t.to_dict() for t in topics])
        self._write(output_dir, "gaps.json", [g.to_dict() for g in gaps])
        self._write(output_dir, "stats.json", self._stats(papers, authors, topics, gaps))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _write(directory: str, filename: str, data: object) -> None:
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    @staticmethod
    def _stats(
        papers: list[Paper],
        authors: list[Author],
        topics: list[Topic],
        gaps: list[ResearchGap],
    ) -> dict:
        venues: dict[str, int] = {}
        for p in papers:
            venues[p.venue] = venues.get(p.venue, 0) + 1

        return {
            "total_papers": len(papers),
            "total_authors": len(authors),
            "total_topics": len(topics),
            "total_gaps": len(gaps),
            "papers_by_source": venues,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
