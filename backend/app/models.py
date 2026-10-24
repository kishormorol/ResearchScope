from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import relationship

from app.database import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(String, primary_key=True)
    source = Column(String, index=True)
    source_type = Column(String, index=True)  # preprint | conference | journal
    title = Column(Text, nullable=False)
    abstract = Column(Text)
    authors = Column(JSONB, default=list)
    year = Column(Integer, index=True)
    published_date = Column(String)
    venue = Column(String, index=True)
    conference_rank = Column(String)
    paper_url = Column(Text)
    pdf_url = Column(Text)
    citations = Column(Integer, default=0)
    tags = Column(JSONB, default=list)
    topics = Column(JSONB, default=list)
    paper_score = Column(Float, default=0.0, index=True)
    paper_type = Column(String)
    difficulty_level = Column(String)
    summary = Column(Text)
    key_contribution = Column(Text)
    why_it_matters = Column(Text)
    one_line_takeaway = Column(Text)
    fetched_at = Column(String)
    search_vector = Column(TSVECTOR)

    favourited_by = relationship("Favourite", back_populates="paper", lazy="dynamic")

    __table_args__ = (
        Index("ix_papers_search", "search_vector", postgresql_using="gin"),
        Index("ix_papers_score_desc", paper_score.desc()),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    favourites = relationship("Favourite", back_populates="user")


class Favourite(Base):
    __tablename__ = "favourites"

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id = Column(
        String, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(DateTime, server_default=func.now())
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="favourites")
    paper = relationship("Paper", back_populates="favourited_by")
