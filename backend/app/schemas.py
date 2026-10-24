from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

# ── Paper ─────────────────────────────────────────────────────────────────────

class PaperOut(BaseModel):
    id: str
    source: str | None = None
    source_type: str | None = None
    title: str
    abstract: str | None = None
    authors: list[str] = []
    year: int | None = None
    published_date: str | None = None
    venue: str | None = None
    conference_rank: str | None = None
    paper_url: str | None = None
    pdf_url: str | None = None
    citations: int = 0
    tags: list[str] = []
    topics: list[str] = []
    paper_score: float = 0.0
    paper_type: str | None = None
    difficulty_level: str | None = None
    summary: str | None = None
    key_contribution: str | None = None
    why_it_matters: str | None = None
    one_line_takeaway: str | None = None

    model_config = {"from_attributes": True}

    # These columns are nullable in the database, but a field default only
    # applies when the key is absent — a present-but-NULL value is validated
    # against the annotation and raises. Because PaperList.results is a
    # list[PaperOut], a single row with a NULL here would otherwise 500 the
    # entire listing, not just that paper. Coerce NULL to the default so
    # partially-populated rows degrade instead of taking the endpoint down.
    @field_validator("authors", "tags", "topics", mode="before")
    @classmethod
    def _null_to_empty_list(cls, value: object) -> object:
        return [] if value is None else value

    @field_validator("citations", mode="before")
    @classmethod
    def _null_to_zero(cls, value: object) -> object:
        return 0 if value is None else value

    @field_validator("paper_score", mode="before")
    @classmethod
    def _null_to_zero_score(cls, value: object) -> object:
        return 0.0 if value is None else value


class PaperList(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[PaperOut]


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdateIn(BaseModel):
    name: str | None = None


# ── Favourites ────────────────────────────────────────────────────────────────

class FavouriteOut(BaseModel):
    paper_id: str
    created_at: datetime
    notes: str | None = None
    paper: PaperOut | None = None

    model_config = {"from_attributes": True}


class FavouriteNoteIn(BaseModel):
    notes: str | None = None


# ── Search ────────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    total: int
    query: str
    results: list[PaperOut]


# ── Pipeline ──────────────────────────────────────────────────────────────────

class PipelineTriggerOut(BaseModel):
    status: str
    message: str
    workflow_run_url: str | None = None
