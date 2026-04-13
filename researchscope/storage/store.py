"""Local TinyDB-backed storage for ResearchScope."""

from __future__ import annotations

from pathlib import Path

from tinydb import Query, TinyDB

from researchscope.models.paper import Paper

_DEFAULT_DB_PATH = Path.home() / ".researchscope" / "papers.json"


class PaperStore:
    """Persistent store for :class:`Paper` objects backed by TinyDB.

    Args:
        db_path: Path to the JSON database file.
            Defaults to ``~/.researchscope/papers.json``.
    """

    def __init__(self, db_path: Path | str = _DEFAULT_DB_PATH) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(db_path)
        self._table = self._db.table("papers")

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    def upsert(self, paper: Paper) -> None:
        """Insert *paper* or update it if a record with the same ID exists."""
        PaperQuery = Query()
        self._table.upsert(
            paper.model_dump(mode="json"),
            PaperQuery.paper_id == paper.paper_id,
        )

    def get(self, paper_id: str) -> Paper | None:
        """Return the paper with the given *paper_id*, or ``None``."""
        PaperQuery = Query()
        record = self._table.get(PaperQuery.paper_id == paper_id)
        return Paper(**record) if record else None

    def all(self) -> list[Paper]:
        """Return all stored papers."""
        return [Paper(**r) for r in self._table.all()]

    def delete(self, paper_id: str) -> bool:
        """Delete the paper with the given *paper_id*.

        Returns:
            ``True`` if a record was removed, ``False`` otherwise.
        """
        PaperQuery = Query()
        removed = self._table.remove(PaperQuery.paper_id == paper_id)
        return bool(removed)

    def count(self) -> int:
        """Return the total number of stored papers."""
        return len(self._table)

    def close(self) -> None:
        """Flush and close the underlying database."""
        self._db.close()

    def __enter__(self) -> PaperStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
