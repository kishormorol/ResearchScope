from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr

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


class PaperList(BaseModel):
    total: int
    page: int
    page_size: int
    results: list[PaperOut]


class PaperViewerOut(BaseModel):
    viewer_url: str | None = None
    external_url: str | None = None


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
