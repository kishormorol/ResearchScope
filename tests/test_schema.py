"""Tests for schema dataclasses."""
from __future__ import annotations

from src.normalization.schema import Author, Paper, ResearchGap, Topic


class TestPaper:
    def test_defaults(self):
        p = Paper()
        assert p.tags == []
        assert p.authors == []
        assert p.difficulty == "intermediate"
        assert p.read_first_score == 0.0
        assert p.citations == 0
        assert p.fetched_at  # non-empty ISO datetime

    def test_roundtrip(self, sample_paper: Paper):
        d = sample_paper.to_dict()
        restored = Paper.from_dict(d)
        assert restored.id == sample_paper.id
        assert restored.title == sample_paper.title
        assert restored.authors == sample_paper.authors
        assert restored.tags == sample_paper.tags

    def test_from_dict_ignores_unknown_keys(self):
        data = {"id": "x", "title": "Test", "unknown_field": "value"}
        p = Paper.from_dict(data)
        assert p.id == "x"
        assert p.title == "Test"

    def test_mutable_defaults_are_independent(self):
        p1 = Paper()
        p2 = Paper()
        p1.tags.append("foo")
        assert p2.tags == []


class TestAuthor:
    def test_defaults(self):
        a = Author()
        assert a.affiliations == []
        assert a.paper_ids == []
        assert a.h_index == 0
        assert a.momentum_score == 0.0

    def test_roundtrip(self):
        a = Author(id="a1", name="Alice", paper_ids=["p1", "p2"], h_index=5)
        restored = Author.from_dict(a.to_dict())
        assert restored.name == "Alice"
        assert restored.paper_ids == ["p1", "p2"]
        assert restored.h_index == 5


class TestTopic:
    def test_defaults(self):
        t = Topic()
        assert t.paper_ids == []
        assert t.prerequisites == []
        assert t.related_topics == []

    def test_roundtrip(self):
        t = Topic(id="t1", name="Transformers", paper_ids=["p1"], difficulty="intermediate")
        restored = Topic.from_dict(t.to_dict())
        assert restored.name == "Transformers"


class TestResearchGap:
    def test_defaults(self):
        g = ResearchGap()
        assert g.source_paper_ids == []
        assert g.suggested_projects == []
        assert g.frequency == 1

    def test_roundtrip(self):
        g = ResearchGap(
            id="g1",
            topic="NLP",
            description="Handling low-resource languages",
            frequency=3,
        )
        restored = ResearchGap.from_dict(g.to_dict())
        assert restored.topic == "NLP"
        assert restored.frequency == 3
