"""Author data model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Author(BaseModel):
    """Represents a researcher / paper author."""

    author_id: str = Field(
        ..., description="Unique identifier (e.g. Semantic Scholar ID)."
    )
    name: str
    affiliations: list[str] = Field(default_factory=list)
    paper_ids: list[str] = Field(
        default_factory=list,
        description="IDs of papers associated with this author.",
    )
    h_index: int = 0
    citation_count: int = 0

    def is_prolific(self, min_papers: int = 10, min_h: int = 5) -> bool:
        """Return True if the author is considered prolific by simple heuristics."""
        return len(self.paper_ids) >= min_papers and self.h_index >= min_h
