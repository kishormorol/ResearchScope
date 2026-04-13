"""
Full normalized data schema for ResearchScope.

All fields are designed to be populated incrementally — connectors fill what
they know; enrichment stages fill the rest.  The from_dict / to_dict helpers
give safe round-trips through JSON without requiring third-party libraries.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Paper
# ---------------------------------------------------------------------------

@dataclass
class Paper:
    # ── identity ────────────────────────────────────────────────────────────
    id: str = ""                     # version-specific, e.g. "arxiv:2501.12345v2"
    canonical_id: str = ""           # dedup-stable ID (same work across sources)
    source: str = ""                 # "arxiv" | "acl_anthology" | …
    source_type: str = "preprint"    # "preprint" | "conference" | "workshop" | "journal"

    # ── bibliographic ────────────────────────────────────────────────────────
    title: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)       # display names
    author_ids: list[str] = field(default_factory=list)    # normalised slugs
    affiliations_raw: list[str] = field(default_factory=list)
    lab_ids: list[str] = field(default_factory=list)
    university_ids: list[str] = field(default_factory=list)
    year: int = 0
    published_date: str = ""         # ISO date
    venue: str = ""                  # human-readable: "arXiv" | "ACL 2024" | …
    conference_rank: str = ""        # "A*" | "A" | "B" | "C" | ""
    paper_url: str = ""
    pdf_url: str = ""
    citations: int = 0

    # ── topics / tags ────────────────────────────────────────────────────────
    topics: list[str] = field(default_factory=list)   # topic-cluster IDs
    tags: list[str] = field(default_factory=list)     # fine-grained keyword tags
    cluster_id: str = ""

    # ── classification ───────────────────────────────────────────────────────
    paper_type: str = ""
    # paper_type values: survey | benchmark | dataset | methods | empirical |
    #                    systems | theory | tutorial | position |
    #                    negative_result | replication

    difficulty_level: str = "L2"     # L1 | L2 | L3 | L4
    difficulty_reason: str = ""
    prerequisites: list[str] = field(default_factory=list)
    maturity_stage: str = "emerging"
    # maturity_stage: foundational | emerging | established | frontier

    # ── scores ───────────────────────────────────────────────────────────────
    paper_score: float = 0.0              # "what matters"
    read_first_score: float = 0.0         # "what should I read first"
    content_potential_score: float = 0.0  # "worth discussing publicly"
    interestingness_score: float = 0.0
    hype_score: float = 0.0
    evidence_strength: float = 0.0
    score_breakdown: dict[str, Any] = field(default_factory=dict)

    # ── content fields ───────────────────────────────────────────────────────
    summary: str = ""
    key_contribution: str = ""
    why_it_matters: str = ""
    content_hook: str = ""
    plain_english_explanation: str = ""
    technical_summary: str = ""
    limitations: list[str] = field(default_factory=list)
    future_work: list[str] = field(default_factory=list)
    research_gap_signals: list[str] = field(default_factory=list)

    # ── creator outputs ──────────────────────────────────────────────────────
    tweet_thread: str = ""
    linkedin_post: str = ""
    newsletter_blurb: str = ""
    video_script_outline: str = ""
    one_line_takeaway: str = ""
    biggest_caveat: str = ""
    read_this_if: str = ""

    # ── metadata ─────────────────────────────────────────────────────────────
    fetched_at: str = field(default_factory=_now_iso)

    # ── backward-compat aliases ──────────────────────────────────────────────
    @property
    def url(self) -> str:
        return self.paper_url

    @url.setter
    def url(self, v: str) -> None:
        self.paper_url = v

    @property
    def difficulty(self) -> str:
        """Return human-readable difficulty label (backward compat)."""
        _map = {"L1": "beginner", "L2": "intermediate", "L3": "advanced", "L4": "frontier"}
        return _map.get(self.difficulty_level, "intermediate")

    @difficulty.setter
    def difficulty(self, v: str) -> None:
        _map = {"beginner": "L1", "intermediate": "L2", "advanced": "L3", "frontier": "L4"}
        self.difficulty_level = _map.get(v, "L2")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # inject computed properties
        d["url"] = self.url
        d["difficulty"] = self.difficulty
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Paper":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        # handle legacy "url" field
        if "url" in data and "paper_url" not in data:
            data = dict(data, paper_url=data["url"])
        # handle legacy "difficulty" string
        if "difficulty" in data and "difficulty_level" not in data:
            _map = {"beginner": "L1", "intermediate": "L2", "advanced": "L3", "frontier": "L4"}
            data = dict(data, difficulty_level=_map.get(data.get("difficulty", ""), "L2"))
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Author
# ---------------------------------------------------------------------------

@dataclass
class Author:
    author_id: str = ""
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    affiliations: list[str] = field(default_factory=list)
    paper_ids: list[str] = field(default_factory=list)
    recent_paper_ids: list[str] = field(default_factory=list)  # last 2 years
    topics: list[str] = field(default_factory=list)
    avg_paper_score: float = 0.0
    momentum_score: float = 0.0
    momentum_breakdown: dict[str, float] = field(default_factory=dict)
    conference_counts: dict[str, int] = field(default_factory=dict)
    lab_ids: list[str] = field(default_factory=list)
    university_ids: list[str] = field(default_factory=list)
    summary_profile: str = ""
    h_index: int = 0

    # ── backward compat ──────────────────────────────────────────────────────
    @property
    def id(self) -> str:
        return self.author_id

    @property
    def top_topics(self) -> list[str]:
        return self.topics[:5]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.author_id
        d["top_topics"] = self.top_topics
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Author":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        if "id" in data and "author_id" not in data:
            data = dict(data, author_id=data["id"])
        if "top_topics" in data and "topics" not in data:
            data = dict(data, topics=data["top_topics"])
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Lab / Organisation
# ---------------------------------------------------------------------------

@dataclass
class Lab:
    lab_id: str = ""
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    university: str = ""
    authors: list[str] = field(default_factory=list)
    paper_ids: list[str] = field(default_factory=list)
    recent_papers: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    avg_paper_score: float = 0.0
    momentum_score: float = 0.0
    a_star_output: int = 0        # # of A* conference papers
    summary_profile: str = ""

    @property
    def id(self) -> str:
        return self.lab_id

    @property
    def top_topics(self) -> list[str]:
        return self.topics[:5]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.lab_id
        d["top_topics"] = self.top_topics
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Lab":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        if "id" in data and "lab_id" not in data:
            data = dict(data, lab_id=data["id"])
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# University
# ---------------------------------------------------------------------------

@dataclass
class University:
    university_id: str = ""
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    papers: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    momentum_score: float = 0.0
    conference_output: dict[str, int] = field(default_factory=dict)
    summary_profile: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "University":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Topic Cluster
# ---------------------------------------------------------------------------

@dataclass
class Topic:
    id: str = ""
    name: str = ""
    keywords: list[str] = field(default_factory=list)
    paper_ids: list[str] = field(default_factory=list)
    trend_score: float = 0.0
    gap_summary: str = ""
    starter_pack_ids: list[str] = field(default_factory=list)   # beginner papers
    frontier_pack_ids: list[str] = field(default_factory=list)  # L4 papers
    difficulty: str = "intermediate"
    prerequisites: list[str] = field(default_factory=list)
    related_topics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Topic":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Research Gap
# ---------------------------------------------------------------------------

@dataclass
class ResearchGap:
    gap_id: str = ""
    topic: str = ""
    title: str = ""
    description: str = ""
    evidence_paper_ids: list[str] = field(default_factory=list)
    gap_type: str = "explicit"   # "explicit" | "pattern" | "starter"
    confidence: float = 0.5
    starter_idea: str = ""
    frequency: int = 1
    suggested_projects: list[str] = field(default_factory=list)

    # ── backward compat ──────────────────────────────────────────────────────
    @property
    def id(self) -> str:
        return self.gap_id

    @property
    def source_paper_ids(self) -> list[str]:
        return self.evidence_paper_ids

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["id"] = self.gap_id
        d["source_paper_ids"] = self.evidence_paper_ids
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchGap":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        if "id" in data and "gap_id" not in data:
            data = dict(data, gap_id=data["id"])
        if "source_paper_ids" in data and "evidence_paper_ids" not in data:
            data = dict(data, evidence_paper_ids=data["source_paper_ids"])
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)
