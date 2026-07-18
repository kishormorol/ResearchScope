from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentStatusOut(BaseModel):
    paper_id: str
    status: str
    page_count: int = 0
    chunk_count: int = 0
    viewer_url: str | None = None
    error_code: str | None = None


class ChatSessionCreate(BaseModel):
    paper_id: str


class ChatSessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    is_archived: bool | None = None


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    status: str
    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionOut(BaseModel):
    id: str
    paper_id: str
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime
    message_count: int = 0
    paper_title: str | None = None

    model_config = {"from_attributes": True}


class ChatSessionDetail(ChatSessionOut):
    messages: list[ChatMessageOut] = Field(default_factory=list)


class ChatSessionList(BaseModel):
    results: list[ChatSessionOut]
    next_cursor: datetime | None = None
