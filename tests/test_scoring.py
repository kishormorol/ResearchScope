"""Tests for PaperScorer."""
from __future__ import annotations

from datetime import datetime, timezone

from src.normalization.schema import Paper
from src.scoring.scorer import PaperScorer

_CURRENT_YEAR = datetime.now(timezone.utc).year


def _paper(year: int, citations: int = 0, abstract: str = "") -> Paper:
    return Paper(
        id=f"p{year}",
        title="Test Paper",
        year=year,
        citations=citations,
        abstract=abstract,
    )


class TestPaperScorer:
    def setup_method(self):
        self.scorer = PaperScorer()

    def test_score_in_range(self, sample_paper):
        result = self.scorer.score(sample_paper)
        assert 0.0 <= result.read_first_score <= 10.0

    def test_newer_paper_scores_higher(self):
        old = self.scorer.score(_paper(_CURRENT_YEAR - 8))
        new = self.scorer.score(_paper(_CURRENT_YEAR))
        assert new.read_first_score > old.read_first_score

    def test_higher_citations_scores_higher(self):
        low = self.scorer.score(_paper(_CURRENT_YEAR, citations=0))
        high = self.scorer.score(_paper(_CURRENT_YEAR, citations=500))
        assert high.read_first_score > low.read_first_score

    def test_longer_abstract_scores_higher(self):
        short = self.scorer.score(_paper(_CURRENT_YEAR, abstract="Short abstract."))
        long_abstract = " ".join(["word"] * 200)
        long = self.scorer.score(_paper(_CURRENT_YEAR, abstract=long_abstract))
        assert long.read_first_score > short.read_first_score

    def test_very_old_paper_has_low_score(self):
        old = self.scorer.score(_paper(_CURRENT_YEAR - 15))
        assert old.read_first_score < 5.0

    def test_score_is_set_on_paper(self, sample_paper):
        result = self.scorer.score(sample_paper)
        assert result is sample_paper
        assert 0.0 <= result.read_first_score <= 10.0
