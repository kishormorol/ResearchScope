"""Tests for data models."""

from datetime import date

from researchscope.models.author import Author
from researchscope.models.paper import Paper


class TestPaper:
    def test_minimal_paper(self):
        paper = Paper(paper_id="2401.00001", title="Test Paper")
        assert paper.paper_id == "2401.00001"
        assert paper.title == "Test Paper"
        assert paper.abstract == ""
        assert paper.authors == []
        assert paper.citation_count == 0

    def test_short_repr_single_author(self):
        paper = Paper(
            paper_id="2401.00001",
            title="Transformers Are Great",
            authors=["Alice Smith"],
            published=date(2024, 1, 15),
        )
        assert "2024-01-15" in paper.short_repr()
        assert "Alice Smith" in paper.short_repr()

    def test_short_repr_many_authors(self):
        paper = Paper(
            paper_id="2401.00002",
            title="Multi-Author Paper",
            authors=["A", "B", "C", "D"],
            published=date(2024, 2, 1),
        )
        assert "et al." in paper.short_repr()

    def test_short_repr_no_date(self):
        paper = Paper(paper_id="x", title="No Date")
        assert "n/d" in paper.short_repr()

    def test_keywords_default_empty(self):
        paper = Paper(paper_id="x", title="Paper")
        assert paper.keywords == []


class TestAuthor:
    def test_minimal_author(self):
        author = Author(author_id="abc123", name="Bob Jones")
        assert author.name == "Bob Jones"
        assert author.h_index == 0

    def test_is_prolific_true(self):
        author = Author(
            author_id="x",
            name="Jane Doe",
            paper_ids=[str(i) for i in range(15)],
            h_index=10,
        )
        assert author.is_prolific()

    def test_is_prolific_false_low_h(self):
        author = Author(
            author_id="x",
            name="New Researcher",
            paper_ids=[str(i) for i in range(20)],
            h_index=2,
        )
        assert not author.is_prolific()

    def test_is_prolific_custom_threshold(self):
        author = Author(
            author_id="x",
            name="Mid Researcher",
            paper_ids=[str(i) for i in range(5)],
            h_index=3,
        )
        assert author.is_prolific(min_papers=5, min_h=3)
