"""Tests for the multi-score system."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.normalization.schema import Paper
from src.scoring.scorer import AuthorMomentumScorer, PaperScorer
from src.normalization.schema import Author

_YEAR = datetime.now(timezone.utc).year


def _paper(year: int, citations: int = 0, abstract: str = "", tags: list[str] | None = None,
           rank: str = "") -> Paper:
    return Paper(
        id=f"p{year}{citations}",
        title="Test Paper",
        year=year,
        citations=citations,
        abstract=abstract,
        tags=tags or [],
        conference_rank=rank,
    )


class TestPaperScorer:
    def setup_method(self):
        self.scorer = PaperScorer()

    def test_all_scores_in_range(self, sample_paper: Paper):
        self.scorer.score(sample_paper)
        assert 0.0 <= sample_paper.paper_score <= 10.0
        assert 0.0 <= sample_paper.read_first_score <= 10.0
        assert 0.0 <= sample_paper.content_potential_score <= 10.0
        assert 0.0 <= sample_paper.interestingness_score <= 10.0

    def test_newer_paper_higher_score(self):
        old  = self.scorer.score(_paper(_YEAR - 8))
        new  = self.scorer.score(_paper(_YEAR))
        assert new.paper_score > old.paper_score

    def test_conference_rank_boosts_paper_score(self):
        no_rank = self.scorer.score(_paper(_YEAR, rank=""))
        a_star  = self.scorer.score(_paper(_YEAR, rank="A*"))
        assert a_star.paper_score > no_rank.paper_score

    def test_high_citations_boost_score(self):
        low  = self.scorer.score(_paper(_YEAR, citations=0))
        high = self.scorer.score(_paper(_YEAR, citations=500))
        assert high.paper_score > low.paper_score

    def test_hot_tags_boost_content_potential(self):
        generic = self.scorer.score(_paper(_YEAR, tags=["Sentiment Analysis"]))
        hot     = self.scorer.score(_paper(_YEAR, tags=["LLMs", "Diffusion Models"]))
        assert hot.content_potential_score > generic.content_potential_score

    def test_score_breakdown_populated(self, sample_paper: Paper):
        self.scorer.score(sample_paper)
        assert "paper_score" in sample_paper.score_breakdown
        bd = sample_paper.score_breakdown["paper_score"]
        assert "recency" in bd
        assert "reason" in bd

    def test_read_first_score_breakdown_populated(self, sample_paper: Paper):
        self.scorer.score(sample_paper)
        assert "read_first_score" in sample_paper.score_breakdown

    def test_content_potential_breakdown_populated(self, sample_paper: Paper):
        self.scorer.score(sample_paper)
        assert "content_potential" in sample_paper.score_breakdown

    def test_score_mutates_paper_in_place(self, sample_paper: Paper):
        result = self.scorer.score(sample_paper)
        assert result is sample_paper

    def test_very_old_paper_low_score(self):
        old = self.scorer.score(_paper(_YEAR - 15))
        assert old.paper_score < 3.0

    def test_novelty_positive_words_boost(self):
        generic = self.scorer.score(_paper(_YEAR, abstract="We compare two methods."))
        novel = self.scorer.score(_paper(
            _YEAR,
            abstract="We propose a novel approach and demonstrate state-of-the-art performance.",
        ))
        assert novel.paper_score >= generic.paper_score


class TestAuthorMomentumScorer:
    def setup_method(self):
        self.scorer = AuthorMomentumScorer()

    def test_score_in_range(self, sample_paper: Paper):
        scorer = PaperScorer()
        scorer.score(sample_paper)
        author = Author(author_id="a1", name="Alice", paper_ids=[sample_paper.id])
        self.scorer.score(author, {sample_paper.id: sample_paper})
        assert 0.0 <= author.momentum_score <= 10.0

    def test_no_papers_gives_zero_momentum(self):
        author = Author(author_id="a2", name="Bob", paper_ids=[])
        self.scorer.score(author, {})
        assert author.momentum_score == 0.0

    def test_recent_papers_boost_momentum(self):
        year = datetime.now(timezone.utc).year
        recent = Paper(id="r1", year=year, tags=["LLMs"], paper_score=7.0)
        old    = Paper(id="o1", year=year - 5, tags=["LLMs"], paper_score=7.0)

        a_recent = Author(author_id="ar", paper_ids=["r1"])
        a_old    = Author(author_id="ao", paper_ids=["o1"])

        self.scorer.score(a_recent, {"r1": recent})
        self.scorer.score(a_old,    {"o1": old})
        assert a_recent.momentum_score >= a_old.momentum_score
