from __future__ import annotations

from datetime import date

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
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
    document = relationship(
        "PaperDocument",
        back_populates="paper",
        uselist=False,
        cascade="all, delete-orphan",
    )
    chat_sessions = relationship("ChatSession", back_populates="paper")

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
    chat_sessions = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan"
    )


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


class PaperDocument(Base):
    __tablename__ = "paper_documents"

    paper_id = Column(
        String, ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    status = Column(String, nullable=False, default="queued", index=True)
    source_url = Column(Text)
    content_hash = Column(String)
    page_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    extractor_version = Column(String, nullable=False, default="pymupdf-hybrid-v2")
    embedding_model = Column(String)
    embedding_dimensions = Column(Integer, default=0)
    error_code = Column(String)
    prepared_at = Column(DateTime(timezone=True))
    last_accessed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    paper = relationship("Paper", back_populates="document")
    chunks = relationship(
        "PaperChunk", back_populates="document", cascade="all, delete-orphan"
    )


class PaperChunk(Base):
    __tablename__ = "paper_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(
        String,
        ForeignKey("paper_documents.paper_id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index = Column(Integer, nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    section = Column(String)
    content = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    parent_chunk_index = Column(Integer)
    content_type = Column(String, nullable=False, default="paragraph")
    embedding = Column(ARRAY(REAL))
    embedding_model = Column(String)
    bounding_box = Column(JSONB)
    search_vector = Column(TSVECTOR)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("PaperDocument", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("paper_id", "chunk_index", name="uq_paper_chunks_order"),
        Index("ix_paper_chunks_paper_page", "paper_id", "page_start"),
        Index("ix_paper_chunks_search", "search_vector", postgresql_using="gin"),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    paper_id = Column(
        String, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String, nullable=False, default="New chat")
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_message_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="chat_sessions")
    paper = relationship("Paper", back_populates="chat_sessions")
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    __table_args__ = (
        Index("ix_chat_sessions_user_recent", "user_id", last_message_at.desc()),
        Index(
            "ix_chat_sessions_user_paper_recent",
            "user_id",
            "paper_id",
            last_message_at.desc(),
        ),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True)
    session_id = Column(
        String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False, default="")
    citations = Column(JSONB, nullable=False, default=list)
    status = Column(String, nullable=False, default="complete", index=True)
    provider = Column(String)
    model = Column(String)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Integer)
    client_request_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        UniqueConstraint(
            "session_id", "client_request_id", name="uq_chat_message_request"
        ),
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )


class ChatUsageDaily(Base):
    __tablename__ = "chat_usage_daily"

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    usage_date = Column(Date, primary_key=True, default=date.today)
    request_count = Column(Integer, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ApiRateLimitWindow(Base):
    __tablename__ = "api_rate_limit_windows"

    scope = Column(String(80), primary_key=True)
    subject_hash = Column(String(64), primary_key=True)
    window_start = Column(DateTime(timezone=True), primary_key=True)
    request_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_api_rate_limit_windows_updated", "updated_at"),)


class ChatGlobalUsageDaily(Base):
    __tablename__ = "chat_global_usage_daily"

    usage_date = Column(Date, primary_key=True, default=date.today)
    provider_request_units = Column(Integer, nullable=False, default=0)
    provider_token_units = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
