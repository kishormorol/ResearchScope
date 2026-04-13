"""Data schema definitions for ResearchScope."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Paper:
    id: str = ""
    title: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    year: int = 0
    venue: str = ""
    url: str = ""
    pdf_url: str = ""
    source: str = ""
    tags: list[str] = field(default_factory=list)
    difficulty: str = "intermediate"
    paper_type: str = ""
    read_first_score: float = 0.0
    citations: int = 0
    summary: str = ""
    why_it_matters: str = ""
    limitations: list[str] = field(default_factory=list)
    future_work: list[str] = field(default_factory=list)
    fetched_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Paper":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class Author:
    id: str = ""
    name: str = ""
    affiliations: list[str] = field(default_factory=list)
    paper_ids: list[str] = field(default_factory=list)
    h_index: int = 0
    momentum_score: float = 0.0
    top_topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Author":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class Lab:
    id: str = ""
    name: str = ""
    university: str = ""
    paper_ids: list[str] = field(default_factory=list)
    top_topics: list[str] = field(default_factory=list)
    momentum_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Lab":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class Topic:
    id: str = ""
    name: str = ""
    paper_ids: list[str] = field(default_factory=list)
    difficulty: str = "intermediate"
    prerequisites: list[str] = field(default_factory=list)
    related_topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Topic":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class ResearchGap:
    id: str = ""
    topic: str = ""
    description: str = ""
    source_paper_ids: list[str] = field(default_factory=list)
    frequency: int = 1
    suggested_projects: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchGap":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)
