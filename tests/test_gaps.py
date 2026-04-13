"""Tests for GapExtractor."""
from __future__ import annotations

from src.gaps.gap_extractor import GapExtractor
from src.normalization.schema import Paper


def _paper(abstract: str, tags: list[str] | None = None) -> Paper:
    return Paper(
        id="g1",
        title="Test Paper",
        abstract=abstract,
        tags=tags or ["NLP"],
    )


class TestGapExtractor:
    def setup_method(self):
        self.extractor = GapExtractor()

    def test_limitation_produces_gap(self):
        p = _paper(
            "Our method works well but a limitation of our approach is the "
            "inability to handle long documents."
        )
        gaps = self.extractor.extract([p])
        assert len(gaps) >= 1

    def test_future_work_produces_gap(self):
        p = _paper(
            "The results are promising. Future work should explore multilingual settings "
            "and better evaluation metrics."
        )
        gaps = self.extractor.extract([p])
        assert len(gaps) >= 1

    def test_suggested_projects_non_empty(self):
        p = _paper(
            "A limitation of our approach is the quadratic complexity.",
            tags=["LLMs"],
        )
        gaps = self.extractor.extract([p])
        assert len(gaps) >= 1
        assert len(gaps[0].suggested_projects) > 0

    def test_no_gap_keywords_no_gap(self):
        p = _paper("We achieve state-of-the-art results on all benchmarks.")
        gaps = self.extractor.extract([p])
        assert gaps == []

    def test_gap_uses_first_tag_as_topic(self):
        p = _paper(
            "Remains to be solved: cross-lingual transfer.",
            tags=["NLP", "Transformers"],
        )
        gaps = self.extractor.extract([p])
        assert gaps[0].topic == "NLP"

    def test_frequency_counts_papers(self):
        p1 = _paper("A limitation is the lack of data.", tags=["NLP"])
        p2 = _paper("Future work includes more experiments.", tags=["NLP"])
        gaps = self.extractor.extract([p1, p2])
        assert gaps[0].frequency == 2
