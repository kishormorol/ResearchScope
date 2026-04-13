"""Tests for analysis utilities."""

from datetime import date, timedelta

from researchscope.analysis.gaps import find_research_gaps
from researchscope.analysis.ranking import rank_papers
from researchscope.models.paper import Paper


def _make_paper(
    paper_id: str,
    citation_count: int = 0,
    days_old: int = 0,
    keywords: list[str] | None = None,
) -> Paper:
    published = date.today() - timedelta(days=days_old)
    return Paper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        citation_count=citation_count,
        published=published,
        keywords=keywords or [],
    )


class TestRankPapers:
    def test_empty_list(self):
        assert rank_papers([]) == []

    def test_higher_citations_ranked_first(self):
        papers = [
            _make_paper("a", citation_count=5),
            _make_paper("b", citation_count=100),
            _make_paper("c", citation_count=20),
        ]
        ranked = rank_papers(papers)
        assert ranked[0].paper_id == "b"

    def test_more_recent_ranked_higher_when_equal_citations(self):
        papers = [
            _make_paper("old", citation_count=0, days_old=300),
            _make_paper("new", citation_count=0, days_old=1),
        ]
        ranked = rank_papers(papers)
        assert ranked[0].paper_id == "new"

    def test_custom_weights(self):
        papers = [
            _make_paper("cited", citation_count=500, days_old=365),
            _make_paper("recent", citation_count=0, days_old=1),
        ]
        # With citations weight 0, recency dominates
        ranked = rank_papers(papers, weights={"citations": 0.0, "recency": 1.0})
        assert ranked[0].paper_id == "recent"

    def test_returns_all_papers(self):
        papers = [_make_paper(str(i)) for i in range(5)]
        assert len(rank_papers(papers)) == 5


class TestFindResearchGaps:
    def test_empty_list(self):
        assert find_research_gaps([]) == []

    def test_returns_least_common_keywords(self):
        papers = [
            _make_paper("1", keywords=["nlp", "nlp", "transformers"]),
            _make_paper("2", keywords=["nlp", "rl"]),
            _make_paper("3", keywords=["nlp", "rl"]),
            _make_paper("4", keywords=["transformers", "rl"]),
        ]
        gaps = find_research_gaps(papers, min_keyword_freq=2)
        # "transformers" and "rl" both appear twice; "nlp" appears 4 times
        # Gaps should surface the least-covered ones first
        assert gaps[0] in ("transformers", "rl")
        assert "nlp" not in gaps[:2]

    def test_min_keyword_freq_filters_noise(self):
        papers = [
            _make_paper("1", keywords=["rare_topic"]),
            _make_paper("2", keywords=["common", "common"]),
        ]
        gaps = find_research_gaps(papers, min_keyword_freq=2)
        assert "rare_topic" not in gaps

    def test_top_n_limits_results(self):
        keywords = [str(i) for i in range(20)]
        papers = [
            _make_paper(str(i), keywords=[kw, kw]) for i, kw in enumerate(keywords)
        ]
        gaps = find_research_gaps(papers, min_keyword_freq=2, top_n=5)
        assert len(gaps) <= 5
