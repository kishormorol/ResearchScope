"""Tests for Deduplicator."""
from __future__ import annotations

from src.dedup.deduplicator import Deduplicator
from src.normalization.schema import Paper


def _paper(title: str, pid: str = "", abstract: str = "") -> Paper:
    return Paper(id=pid or title[:8], title=title, abstract=abstract)


class TestDeduplicator:
    def setup_method(self):
        self.dedup = Deduplicator(threshold=0.85)

    def test_exact_title_match(self):
        p1 = _paper("Attention Is All You Need", "p1")
        p2 = _paper("Attention Is All You Need", "p2")
        result = self.dedup.deduplicate([p1, p2])
        assert len(result) == 1

    def test_similar_title_deduped(self):
        p1 = _paper("Attention Is All You Need Revisited", "p1")
        p2 = _paper("Attention Is All You Need Revisited", "p2")
        result = self.dedup.deduplicate([p1, p2])
        assert len(result) == 1

    def test_different_titles_not_deduped(self):
        p1 = _paper("BERT: Pre-training of Deep Bidirectional Transformers", "p1")
        p2 = _paper("GPT-3: Language Models are Few-Shot Learners", "p2")
        result = self.dedup.deduplicate([p1, p2])
        assert len(result) == 2

    def test_prefers_more_complete_paper(self):
        p1 = _paper("Shared Title", "p1", abstract="")
        p2 = _paper("Shared Title", "p2", abstract="A full abstract here.")
        result = self.dedup.deduplicate([p1, p2])
        assert len(result) == 1
        assert result[0].id == "p2"

    def test_empty_list(self):
        assert self.dedup.deduplicate([]) == []

    def test_single_paper(self, sample_paper):
        result = self.dedup.deduplicate([sample_paper])
        assert len(result) == 1
