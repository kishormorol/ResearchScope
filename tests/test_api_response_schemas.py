"""Response-schema tests for the backend API.

These guard a specific trap: a Pydantic field default only applies when the key
is *absent*. A present-but-NULL value is validated against the annotation and
raises, so a nullable database column mapped to a non-optional field turns into
an HTTP 500. Because list responses embed these models, one bad row would take
down an entire endpoint rather than degrading a single record.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.schemas import PaperList, PaperOut  # noqa: E402

# Columns that are nullable in the papers table but non-optional on PaperOut.
_NULLABLE_PAPER_FIELDS = {
    "authors": [],
    "tags": [],
    "topics": [],
    "citations": 0,
    "paper_score": 0.0,
}


class _Row:
    """Stand-in for an ORM row (PaperOut uses from_attributes)."""

    def __init__(self, **values):
        defaults = {
            "id": "arxiv:1706.03762",
            "source": "arxiv",
            "source_type": None,
            "title": "Attention Is All You Need",
            "abstract": None,
            "authors": None,
            "year": None,
            "published_date": None,
            "venue": None,
            "conference_rank": None,
            "paper_url": None,
            "pdf_url": None,
            "citations": None,
            "tags": None,
            "topics": None,
            "paper_score": None,
            "paper_type": None,
            "difficulty_level": None,
            "summary": None,
            "key_contribution": None,
            "why_it_matters": None,
            "one_line_takeaway": None,
        }
        defaults.update(values)
        for key, value in defaults.items():
            setattr(self, key, value)


def test_paper_with_all_null_optional_columns_serializes():
    paper = PaperOut.model_validate(_Row())
    for field, expected in _NULLABLE_PAPER_FIELDS.items():
        assert getattr(paper, field) == expected


def test_each_nullable_paper_field_coerces_independently():
    for field, expected in _NULLABLE_PAPER_FIELDS.items():
        paper = PaperOut.model_validate(_Row(**{field: None}))
        assert getattr(paper, field) == expected, field


def test_one_null_row_does_not_break_the_whole_paper_list():
    """PaperList.results is list[PaperOut] — one bad row used to 500 the page."""
    listing = PaperList.model_validate(
        {
            "total": 2,
            "page": 1,
            "page_size": 50,
            "results": [_Row(), _Row(id="arxiv:2401.00001", authors=["A. Author"])],
        }
    )
    assert len(listing.results) == 2
    assert listing.results[0].authors == []
    assert listing.results[1].authors == ["A. Author"]


def test_populated_paper_values_are_preserved():
    paper = PaperOut.model_validate(
        _Row(
            authors=["Ashish Vaswani"],
            tags=["transformers"],
            topics=["NLP"],
            citations=173000,
            paper_score=9.5,
        )
    )
    assert paper.authors == ["Ashish Vaswani"]
    assert paper.tags == ["transformers"]
    assert paper.topics == ["NLP"]
    assert paper.citations == 173000
    assert paper.paper_score == 9.5
