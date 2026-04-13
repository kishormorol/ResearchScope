"""Tests for schema dataclasses."""
from __future__ import annotations

from src.normalization.schema import Author, Lab, Paper, ResearchGap, Topic, University


class TestPaper:
    def test_defaults(self):
        p = Paper()
        assert p.tags == []
        assert p.authors == []
        assert p.difficulty_level == "L2"
        assert p.paper_score == 0.0
        assert p.read_first_score == 0.0
        assert p.content_potential_score == 0.0
        assert p.citations == 0
        assert p.fetched_at  # non-empty ISO datetime

    def test_difficulty_property(self):
        p = Paper(difficulty_level="L1")
        assert p.difficulty == "beginner"
        p.difficulty = "advanced"
        assert p.difficulty_level == "L3"

    def test_url_compat(self):
        p = Paper(paper_url="https://example.com/paper")
        assert p.url == "https://example.com/paper"
        p.url = "https://example.com/new"
        assert p.paper_url == "https://example.com/new"

    def test_roundtrip(self, sample_paper: Paper):
        d = sample_paper.to_dict()
        restored = Paper.from_dict(d)
        assert restored.id == sample_paper.id
        assert restored.title == sample_paper.title
        assert restored.authors == sample_paper.authors
        assert restored.tags == sample_paper.tags
        assert restored.difficulty_level == sample_paper.difficulty_level

    def test_roundtrip_preserves_score_breakdown(self, sample_paper: Paper):
        sample_paper.score_breakdown = {"paper_score": {"score": 7.5, "reason": "ok"}}
        d = sample_paper.to_dict()
        restored = Paper.from_dict(d)
        assert restored.score_breakdown["paper_score"]["score"] == 7.5

    def test_from_dict_ignores_unknown_keys(self):
        p = Paper.from_dict({"id": "x", "title": "T", "unknown_field": "value"})
        assert p.id == "x"
        assert p.title == "T"

    def test_from_dict_legacy_url(self):
        p = Paper.from_dict({"id": "x", "url": "https://example.com"})
        assert p.paper_url == "https://example.com"

    def test_from_dict_legacy_difficulty(self):
        p = Paper.from_dict({"id": "x", "difficulty": "advanced"})
        assert p.difficulty_level == "L3"

    def test_mutable_defaults_independent(self):
        p1, p2 = Paper(), Paper()
        p1.tags.append("foo")
        assert p2.tags == []

    def test_to_dict_includes_computed_fields(self, sample_paper: Paper):
        d = sample_paper.to_dict()
        assert "url" in d
        assert "difficulty" in d


class TestAuthor:
    def test_defaults(self):
        a = Author()
        assert a.affiliations == []
        assert a.paper_ids == []
        assert a.momentum_score == 0.0
        assert a.avg_paper_score == 0.0

    def test_id_property(self):
        a = Author(author_id="alice_smith")
        assert a.id == "alice_smith"

    def test_top_topics_truncated(self):
        a = Author(topics=[str(i) for i in range(10)])
        assert len(a.top_topics) == 5

    def test_roundtrip(self):
        a = Author(author_id="a1", name="Alice", paper_ids=["p1", "p2"])
        restored = Author.from_dict(a.to_dict())
        assert restored.name == "Alice"
        assert restored.paper_ids == ["p1", "p2"]

    def test_from_dict_legacy_id(self):
        a = Author.from_dict({"id": "a1", "name": "Bob"})
        assert a.author_id == "a1"


class TestLab:
    def test_defaults(self):
        l = Lab()
        assert l.paper_ids == []
        assert l.topics == []
        assert l.a_star_output == 0

    def test_roundtrip(self):
        l = Lab(lab_id="openai", name="OpenAI", topics=["LLMs"])
        restored = Lab.from_dict(l.to_dict())
        assert restored.name == "OpenAI"
        assert restored.topics == ["LLMs"]


class TestUniversity:
    def test_defaults(self):
        u = University()
        assert u.papers == []
        assert u.authors == []
        assert u.momentum_score == 0.0

    def test_roundtrip(self):
        u = University(university_id="mit", name="MIT", papers=["p1"])
        restored = University.from_dict(u.to_dict())
        assert restored.name == "MIT"
        assert restored.papers == ["p1"]


class TestTopic:
    def test_defaults(self):
        t = Topic()
        assert t.paper_ids == []
        assert t.starter_pack_ids == []
        assert t.frontier_pack_ids == []
        assert t.trend_score == 0.0

    def test_roundtrip(self):
        t = Topic(id="llms", name="LLMs", paper_ids=["p1", "p2"], trend_score=8.5)
        restored = Topic.from_dict(t.to_dict())
        assert restored.name == "LLMs"
        assert restored.trend_score == 8.5


class TestResearchGap:
    def test_defaults(self):
        g = ResearchGap()
        assert g.evidence_paper_ids == []
        assert g.gap_type == "explicit"
        assert g.confidence == 0.5
        assert g.frequency == 1

    def test_backward_compat(self):
        g = ResearchGap(gap_id="g1", evidence_paper_ids=["p1"])
        assert g.id == "g1"
        assert g.source_paper_ids == ["p1"]

    def test_roundtrip(self):
        g = ResearchGap(
            gap_id="g1",
            topic="NLP",
            title="Low-resource challenge",
            frequency=5,
            gap_type="pattern",
            confidence=0.7,
        )
        restored = ResearchGap.from_dict(g.to_dict())
        assert restored.topic == "NLP"
        assert restored.frequency == 5
        assert restored.gap_type == "pattern"
