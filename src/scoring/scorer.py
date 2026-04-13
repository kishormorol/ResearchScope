"""Paper scoring logic."""
from __future__ import annotations

from datetime import datetime, timezone

from src.normalization.schema import Paper

_CURRENT_YEAR = datetime.now(timezone.utc).year
_MAX_AGE = 10  # papers older than this get zero recency score


class PaperScorer:
    """Compute a read_first_score (0–10) for a paper."""

    def score(self, paper: Paper) -> Paper:
        recency = self._recency_score(paper.year)
        citation = self._citation_score(paper.citations)
        completeness = self._completeness_score(paper.abstract)

        raw = recency * 0.5 + citation * 0.35 + completeness * 0.15
        paper.read_first_score = round(min(max(raw, 0.0), 10.0), 2)
        return paper

    # ------------------------------------------------------------------
    # Component scores (each 0–10)
    # ------------------------------------------------------------------

    @staticmethod
    def _recency_score(year: int) -> float:
        if not year:
            return 0.0
        age = _CURRENT_YEAR - year
        if age < 0:
            return 10.0
        if age >= _MAX_AGE:
            return 0.0
        return round(10.0 * (1 - age / _MAX_AGE), 2)

    @staticmethod
    def _citation_score(citations: int) -> float:
        if not citations:
            return 0.0
        # Logarithmic scale: 1000+ citations → ~10
        import math

        return round(min(10.0 * math.log1p(citations) / math.log1p(1000), 10.0), 2)

    @staticmethod
    def _completeness_score(abstract: str) -> float:
        words = len(abstract.split()) if abstract else 0
        # Ideal abstract: ~250 words
        return round(min(words / 25.0, 10.0), 2)
