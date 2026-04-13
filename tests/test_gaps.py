"""Tests for GapExtractor (3-layer)."""
from __future__ import annotations

import pytest

from src.gaps.gap_extractor import GapExtractor
from src.normalization.schema import Paper


def _paper(abstract: str, pid: str = "g1", tags: list[str] | None = None) -> Paper:
    return Paper(id=pid, title="Test Paper", abstract=abstract, tags=tags or ["NLP"])


class TestGapExtractorLayer1:
    """Layer 1 — explicit gaps from limitation/future-work language."""

    def setup_method(self):
        self.extractor = GapExtractor()

    def test_limitation_produces_explicit_gap(self):
        p = _paper(
            "Our method works well but a limitation of our approach is the "
            "inability to handle long documents."
        )
        gaps = self.extractor.extract([p])
        explicit = [g for g in gaps if g.gap_type == "explicit"]
        assert len(explicit) >= 1

    def test_future_work_produces_gap(self):
        p = _paper(
            "Future work should explore multilingual settings and better evaluation metrics."
        )
        gaps = self.extractor.extract([p])
        assert len(gaps) >= 1

    def test_gap_has_title(self):
        p = _paper("A limitation of our approach is the quadratic complexity.", tags=["LLMs"])
        gaps = self.extractor.extract([p])
        explicit = [g for g in gaps if g.gap_type == "explicit"]
        assert explicit[0].title  # non-empty title

    def test_suggested_projects_non_empty(self):
        p = _paper("A limitation of our approach is the quadratic complexity.", tags=["LLMs"])
        gaps = self.extractor.extract([p])
        assert any(g.suggested_projects for g in gaps)

    def test_no_gap_language_no_explicit_gap(self):
        p = _paper("We achieve state-of-the-art results on all benchmarks.")
        gaps = self.extractor.extract([p])
        explicit = [g for g in gaps if g.gap_type == "explicit"]
        assert len(explicit) == 0

    def test_gap_topic_from_first_tag(self):
        p = _paper("Remains to be solved: cross-lingual transfer.", tags=["NLP", "Transformers"])
        gaps = [g for g in self.extractor.extract([p]) if g.gap_type == "explicit"]
        assert gaps[0].topic == "NLP"

    def test_confidence_explicit_is_high(self):
        p = _paper("A limitation of our approach is the quadratic complexity.")
        gaps = [g for g in self.extractor.extract([p]) if g.gap_type == "explicit"]
        if gaps:
            assert gaps[0].confidence >= 0.7


class TestGapExtractorLayer2:
    """Layer 2 — pattern gaps from recurring signals across papers."""

    def setup_method(self):
        self.extractor = GapExtractor()

    def test_robustness_pattern_detected(self):
        papers = [
            _paper("The model lacks robustness to distribution shift.", pid=f"p{i}")
            for i in range(3)
        ]
        gaps = self.extractor.extract(papers)
        pattern_gaps = [g for g in gaps if g.gap_type == "pattern"]
        assert len(pattern_gaps) >= 1

    def test_pattern_requires_at_least_2_papers(self):
        p = _paper("The model lacks robustness to adversarial examples.")
        gaps = self.extractor.extract([p])
        pattern_gaps = [g for g in gaps if g.gap_type == "pattern"]
        # Single paper should not produce a pattern gap
        assert len(pattern_gaps) == 0

    def test_hallucination_pattern(self):
        papers = [
            _paper("LLMs suffer from hallucination in factual queries.", pid=f"h{i}")
            for i in range(3)
        ]
        gaps = self.extractor.extract(papers)
        pattern_gaps = [g for g in gaps if g.gap_type == "pattern"]
        assert any("hallucin" in g.title.lower() or "factual" in g.title.lower() for g in pattern_gaps)


class TestGapExtractorLayer3:
    """Layer 3 — starter ideas."""

    def setup_method(self):
        self.extractor = GapExtractor()

    def test_starter_gaps_generated_for_known_tags(self):
        papers = [
            _paper("We study LLMs.", pid=f"l{i}", tags=["LLMs"])
            for i in range(5)
        ]
        gaps = self.extractor.extract(papers)
        starter = [g for g in gaps if g.gap_type == "starter"]
        assert len(starter) >= 1

    def test_starter_gap_has_idea(self):
        papers = [_paper("Reinforcement learning experiment.", pid=f"r{i}", tags=["RL"]) for i in range(3)]
        gaps = self.extractor.extract(papers)
        starter = [g for g in gaps if g.gap_type == "starter"]
        if starter:
            assert len(starter[0].starter_idea) > 10


class TestGapExtractorGeneral:
    def setup_method(self):
        self.extractor = GapExtractor()

    def test_all_gaps_have_gap_id(self, sample_papers):
        gaps = self.extractor.extract(sample_papers)
        assert all(g.gap_id for g in gaps)

    def test_all_gaps_have_topic(self, sample_papers):
        gaps = self.extractor.extract(sample_papers)
        assert all(g.topic for g in gaps)

    def test_frequency_positive(self, sample_papers):
        gaps = self.extractor.extract(sample_papers)
        assert all(g.frequency >= 1 for g in gaps)
