"""Tests for the PaperStore storage layer."""

from pathlib import Path

import pytest

from researchscope.models.paper import Paper
from researchscope.storage.store import PaperStore


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    """Return a PaperStore backed by a temporary file."""
    return PaperStore(db_path=tmp_path / "test_papers.json")


@pytest.fixture
def sample_paper() -> Paper:
    return Paper(
        paper_id="2401.00001",
        title="Sample Paper",
        authors=["Alice", "Bob"],
        citation_count=42,
    )


class TestPaperStore:
    def test_initial_count_is_zero(self, store: PaperStore) -> None:
        assert store.count() == 0

    def test_upsert_and_get(self, store: PaperStore, sample_paper: Paper) -> None:
        store.upsert(sample_paper)
        retrieved = store.get(sample_paper.paper_id)
        assert retrieved is not None
        assert retrieved.paper_id == sample_paper.paper_id
        assert retrieved.title == sample_paper.title

    def test_upsert_updates_existing(
        self, store: PaperStore, sample_paper: Paper
    ) -> None:
        store.upsert(sample_paper)
        updated = sample_paper.model_copy(update={"title": "Updated Title"})
        store.upsert(updated)
        assert store.count() == 1
        assert store.get(sample_paper.paper_id).title == "Updated Title"

    def test_get_missing_returns_none(self, store: PaperStore) -> None:
        assert store.get("nonexistent-id") is None

    def test_all_returns_all_papers(self, store: PaperStore) -> None:
        papers = [Paper(paper_id=str(i), title=f"Paper {i}") for i in range(5)]
        for paper in papers:
            store.upsert(paper)
        assert len(store.all()) == 5

    def test_all_empty_store(self, store: PaperStore) -> None:
        assert store.all() == []

    def test_delete_existing_paper(
        self, store: PaperStore, sample_paper: Paper
    ) -> None:
        store.upsert(sample_paper)
        result = store.delete(sample_paper.paper_id)
        assert result is True
        assert store.get(sample_paper.paper_id) is None
        assert store.count() == 0

    def test_delete_nonexistent_returns_false(self, store: PaperStore) -> None:
        assert store.delete("no-such-id") is False

    def test_count_reflects_insertions(self, store: PaperStore) -> None:
        for i in range(3):
            store.upsert(Paper(paper_id=str(i), title=f"Paper {i}"))
        assert store.count() == 3

    def test_context_manager(self, tmp_path: Path, sample_paper: Paper) -> None:
        db_path = tmp_path / "ctx_papers.json"
        with PaperStore(db_path=db_path) as store:
            store.upsert(sample_paper)
            assert store.count() == 1
        # Re-open to verify persistence
        with PaperStore(db_path=db_path) as store2:
            assert store2.count() == 1
            assert store2.get(sample_paper.paper_id) is not None

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        nested_path = tmp_path / "nested" / "dir" / "papers.json"
        store = PaperStore(db_path=nested_path)
        assert nested_path.parent.exists()
        store.close()
