"""Paper data model."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Paper(BaseModel):
    """Represents a research paper."""

    paper_id: str = Field(..., description="Unique identifier (e.g. arXiv ID or DOI).")
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    published: date | None = None
    url: str = ""
    source: str = Field(
        default="unknown",
        description="Origin of the record, e.g. 'arxiv' or 'semantic_scholar'.",
    )
    citation_count: int = 0
    keywords: list[str] = Field(default_factory=list)

    def short_repr(self) -> str:
        """Return a one-line summary of the paper."""
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += " et al."
        date_str = str(self.published) if self.published else "n/d"
        return f"[{date_str}] {self.title} — {authors_str}"
