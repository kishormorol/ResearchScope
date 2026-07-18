from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import ChatMessage, ChatSession, Paper, User
from app.schemas_chat import (
    ChatMessageCreate,
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionList,
    ChatSessionOut,
    ChatSessionUpdate,
)
from app.services.chat_service import ChatError, start_turn, stream_chat_turn
from app.services.quota_service import (
    QuotaConfigurationError,
    QuotaExceeded,
    client_ip,
    enforce_chat_request_limits,
)

router = APIRouter(prefix="/chat", tags=["paper-chat"])


async def _owned_session(
    db: AsyncSession, user_id: int, session_id: str
) -> ChatSession:
    session = (
        await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id, ChatSession.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


async def _session_out(db: AsyncSession, session: ChatSession) -> ChatSessionOut:
    count = (
        await db.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session.id)
        )
    ).scalar_one()
    paper = await db.get(Paper, session.paper_id)
    return ChatSessionOut(
        id=session.id,
        paper_id=session.paper_id,
        title=session.title,
        is_archived=session.is_archived,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at,
        message_count=count,
        paper_title=paper.title if paper else None,
    )


@router.post("/sessions", response_model=ChatSessionOut, status_code=201)
async def create_session(
    body: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(Paper, body.paper_id):
        raise HTTPException(status_code=404, detail="Paper not found")
    now = datetime.now(timezone.utc)
    session = ChatSession(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        paper_id=body.paper_id,
        title="New chat",
        created_at=now,
        updated_at=now,
        last_message_at=now,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


@router.get("/sessions", response_model=ChatSessionList)
async def list_sessions(
    paper_id: str | None = None,
    cursor: datetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ChatSession).where(ChatSession.user_id == current_user.id)
    if paper_id:
        stmt = stmt.where(ChatSession.paper_id == paper_id)
    if cursor:
        stmt = stmt.where(ChatSession.last_message_at < cursor)
    rows = list(
        (
            await db.execute(
                stmt.order_by(ChatSession.last_message_at.desc()).limit(limit + 1)
            )
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return ChatSessionList(
        results=[await _session_out(db, row) for row in rows],
        next_cursor=rows[-1].last_message_at if has_more and rows else None,
    )


@router.delete("/sessions", status_code=204)
async def delete_all_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(delete(ChatSession).where(ChatSession.user_id == current_user.id))
    await db.commit()


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, current_user.id, session_id)
    messages = list(
        (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session.id)
                .order_by(ChatMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    base = await _session_out(db, session)
    return ChatSessionDetail(**base.model_dump(), messages=messages)


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def update_session(
    session_id: str,
    body: ChatSessionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, current_user.id, session_id)
    if body.title is not None:
        session.title = body.title.strip()
    if body.is_archived is not None:
        session.is_archived = body.is_archived
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, current_user.id, session_id)
    await db.delete(session)
    await db.commit()


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_session(db, current_user.id, session_id)
    return list(
        (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            )
        )
        .scalars()
        .all()
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: ChatMessageCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    session = await _owned_session(db, current_user.id, session_id)
    try:
        await enforce_chat_request_limits(current_user.id, client_ip(request))
    except QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=exc.code) from exc
    except QuotaConfigurationError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    try:
        turn = await start_turn(
            db, session, current_user, body.content.strip(), idempotency_key
        )
    except ChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code)
    return StreamingResponse(
        stream_chat_turn(db, turn, current_user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
