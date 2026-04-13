"""Tests for the aggregation module."""
from __future__ import annotations

from datetime import datetime, timezone

from src.aggregation.aggregator import Aggregator, _author_slug, _match_lab, _match_university
from src.normalization.schema import Paper

_YEAR = datetime.now(timezone.utc).year


def _paper(pid: str, authors: list[str], tags: list[str], year: int = _YEAR,
           rank: str = "", affiliations: list[str] | None = None) -> Paper:
    return Paper(
        id=pid,
        title=f"Paper {pid}",
        abstract="We propose a novel method.",
        authors=authors,
        year=year,
        tags=tags,
        conference_rank=rank,
        affiliations_raw=affiliations or [],
        paper_score=7.0,
    )


class TestAuthorSlug:
    def test_basic(self):
        assert _author_slug("Alice Smith") == "alice_smith"

    def test_special_chars(self):
        slug = _author_slug("Jean-Pierre Müller")
        assert " " not in slug
        assert len(slug) > 0


class TestUniversityMatching:
    def test_stanford(self):
        assert _match_university("Stanford University, CA") == "Stanford University"

    def test_mit(self):
        assert _match_university("MIT CSAIL") == "MIT"

    def test_cmu(self):
        assert _match_university("Carnegie Mellon University") == "Carnegie Mellon University"

    def test_none_for_unknown(self):
        assert _match_university("Unknown Institute of Tech") is None


class TestLabMatching:
    def test_deepmind(self):
        assert _match_lab("Google DeepMind, London") == "DeepMind"

    def test_openai(self):
        assert _match_lab("OpenAI, San Francisco") == "OpenAI"

    def test_none_for_university(self):
        assert _match_lab("MIT CSAIL") is None


class TestAggregatorAuthors:
    def setup_method(self):
        self.agg = Aggregator()

    def test_builds_author_for_each_unique_name(self):
        papers = [
            _paper("p1", ["Alice Smith", "Bob Jones"], ["LLMs"]),
            _paper("p2", ["Alice Smith", "Carol Lee"], ["Transformers"]),
        ]
        authors = self.agg.build_authors(papers)
        names = {a.name for a in authors}
        assert "Alice Smith" in names
        assert "Bob Jones" in names
        assert "Carol Lee" in names

    def test_paper_ids_accumulated(self):
        papers = [
            _paper("p1", ["Alice Smith"], ["LLMs"]),
            _paper("p2", ["Alice Smith"], ["Transformers"]),
        ]
        authors = self.agg.build_authors(papers)
        alice = next(a for a in authors if a.name == "Alice Smith")
        assert len(alice.paper_ids) == 2

    def test_recent_paper_ids_only_last_2_years(self):
        papers = [
            _paper("p1", ["Alice Smith"], ["LLMs"], year=_YEAR),
            _paper("p2", ["Alice Smith"], ["LLMs"], year=_YEAR - 5),
        ]
        authors = self.agg.build_authors(papers)
        alice = next(a for a in authors if a.name == "Alice Smith")
        assert "p1" in alice.recent_paper_ids
        assert "p2" not in alice.recent_paper_ids

    def test_topics_accumulated(self):
        papers = [
            _paper("p1", ["Alice Smith"], ["LLMs"]),
            _paper("p2", ["Alice Smith"], ["Transformers"]),
        ]
        authors = self.agg.build_authors(papers)
        alice = next(a for a in authors if a.name == "Alice Smith")
        assert "LLMs" in alice.topics
        assert "Transformers" in alice.topics

    def test_summary_profile_populated(self):
        papers = [_paper("p1", ["Alice Smith"], ["LLMs"])]
        authors = self.agg.build_authors(papers)
        alice = next(a for a in authors if a.name == "Alice Smith")
        assert len(alice.summary_profile) > 20

    def test_sorted_by_paper_count_desc(self):
        papers = [
            _paper("p1", ["Alice Smith"], ["LLMs"]),
            _paper("p2", ["Alice Smith"], ["LLMs"]),
            _paper("p3", ["Bob Jones"], ["NLP"]),
        ]
        authors = self.agg.build_authors(papers)
        assert authors[0].name == "Alice Smith"


class TestAggregatorLabs:
    def setup_method(self):
        self.agg = Aggregator()

    def test_lab_inferred_from_affiliation(self):
        papers = [_paper("p1", ["Alice"], ["LLMs"], affiliations=["OpenAI, San Francisco"])]
        labs = self.agg.build_labs(papers)
        lab_names = {l.name for l in labs}
        assert "OpenAI" in lab_names

    def test_a_star_counted(self):
        papers = [
            _paper("p1", ["Alice"], ["LLMs"], rank="A*", affiliations=["OpenAI"]),
            _paper("p2", ["Alice"], ["LLMs"], rank="A", affiliations=["OpenAI"]),
        ]
        labs = self.agg.build_labs(papers)
        openai = next((l for l in labs if l.name == "OpenAI"), None)
        if openai:
            assert openai.a_star_output >= 1


class TestAggregatorUniversities:
    def setup_method(self):
        self.agg = Aggregator()

    def test_university_inferred_from_affiliation(self):
        papers = [_paper("p1", ["Alice"], ["LLMs"], affiliations=["Stanford University, CA"])]
        unis = self.agg.build_universities(papers)
        uni_names = {u.name for u in unis}
        assert "Stanford University" in uni_names

    def test_paper_accumulated(self):
        papers = [
            _paper("p1", ["Alice"], ["LLMs"], affiliations=["MIT CSAIL"]),
            _paper("p2", ["Bob"], ["NLP"], affiliations=["MIT Lab"]),
        ]
        unis = self.agg.build_universities(papers)
        mit = next((u for u in unis if u.name == "MIT"), None)
        assert mit is not None
        assert len(mit.papers) >= 2
