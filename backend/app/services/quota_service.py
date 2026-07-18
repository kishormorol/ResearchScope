from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import and_, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_session_factory
from app.models import ApiRateLimitWindow, ChatGlobalUsageDaily

log = logging.getLogger(__name__)
_CLEANUP_LOCK = asyncio.Lock()
_NEXT_CLEANUP_AT = 0.0


class QuotaError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class QuotaExceeded(QuotaError):
    pass


class GlobalCostLimitExceeded(QuotaError):
    pass


class QuotaConfigurationError(QuotaError):
    pass


def _nonnegative_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise QuotaConfigurationError("quota_configuration_invalid") from exc
    if value < 0:
        raise QuotaConfigurationError("quota_configuration_invalid")
    return value


def _window_start(now: datetime, window_seconds: int) -> datetime:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    timestamp = int(now.astimezone(timezone.utc).timestamp())
    return datetime.fromtimestamp(
        timestamp - (timestamp % window_seconds), tz=timezone.utc
    )


def client_ip(request: Request) -> str:
    # The ASGI server should be configured with its trusted proxy list. Reading
    # request.client avoids accepting a spoofable forwarded header here.
    return request.client.host if request.client else "unknown"


def _subject_hash(scope: str, subject: str) -> str:
    return hashlib.sha256(f"{scope}:{subject}".encode()).hexdigest()


async def _maybe_cleanup_windows() -> None:
    global _NEXT_CLEANUP_AT
    if time.monotonic() < _NEXT_CLEANUP_AT:
        return
    async with _CLEANUP_LOCK:
        if time.monotonic() < _NEXT_CLEANUP_AT:
            return
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            async with get_session_factory()() as db:
                await db.execute(
                    delete(ApiRateLimitWindow).where(
                        ApiRateLimitWindow.updated_at < cutoff
                    )
                )
                await db.commit()
        except Exception:
            log.warning("Rate-limit retention cleanup failed", exc_info=True)
        finally:
            _NEXT_CLEANUP_AT = time.monotonic() + 3_600


async def consume_rate_limit(
    scope: str,
    subject: str,
    *,
    limit: int,
    window_seconds: int,
    now: datetime | None = None,
) -> None:
    """Atomically consume one fixed-window unit across all app instances."""
    if limit == 0:
        return
    if limit < 0 or window_seconds <= 0:
        raise QuotaConfigurationError("quota_configuration_invalid")
    window = _window_start(now or datetime.now(timezone.utc), window_seconds)
    stmt = (
        pg_insert(ApiRateLimitWindow)
        .values(
            scope=scope,
            subject_hash=_subject_hash(scope, subject),
            window_start=window,
            request_count=1,
        )
        .on_conflict_do_update(
            index_elements=[
                ApiRateLimitWindow.scope,
                ApiRateLimitWindow.subject_hash,
                ApiRateLimitWindow.window_start,
            ],
            set_={
                "request_count": ApiRateLimitWindow.request_count + 1,
                "updated_at": func.now(),
            },
            where=ApiRateLimitWindow.request_count < limit,
        )
        .returning(ApiRateLimitWindow.request_count)
    )
    async with get_session_factory()() as db:
        consumed = (await db.execute(stmt)).scalar_one_or_none()
        if consumed is None:
            await db.rollback()
            raise QuotaExceeded(f"{scope}_rate_limit_reached")
        await db.commit()
    await _maybe_cleanup_windows()


async def enforce_chat_request_limits(user_id: int, ip_address: str) -> None:
    await consume_rate_limit(
        "chat_user",
        str(user_id),
        limit=_nonnegative_int("CHAT_USER_REQUESTS_PER_MINUTE", 10),
        window_seconds=60,
    )
    await consume_rate_limit(
        "chat_ip",
        ip_address,
        limit=_nonnegative_int("CHAT_IP_REQUESTS_PER_MINUTE", 30),
        window_seconds=60,
    )


async def enforce_prepare_limits(user_id: int, ip_address: str) -> None:
    await consume_rate_limit(
        "prepare_user",
        str(user_id),
        limit=_nonnegative_int("CHAT_PREPARES_PER_USER_PER_DAY", 5),
        window_seconds=86_400,
    )
    await consume_rate_limit(
        "prepare_ip",
        ip_address,
        limit=_nonnegative_int("CHAT_PREPARES_PER_IP_PER_DAY", 20),
        window_seconds=86_400,
    )


async def enforce_pdf_limit(ip_address: str) -> None:
    await consume_rate_limit(
        "pdf_ip",
        ip_address,
        limit=_nonnegative_int("CHAT_PDF_REQUESTS_PER_IP_PER_MINUTE", 60),
        window_seconds=60,
    )


async def reserve_global_provider_budget(
    estimated_tokens: int, *, requests: int = 1
) -> None:
    """Reserve conservative provider units before making a billable request."""
    request_limit = _nonnegative_int("CHAT_GLOBAL_DAILY_PROVIDER_REQUEST_BUDGET", 500)
    token_limit = _nonnegative_int("CHAT_GLOBAL_DAILY_PROVIDER_TOKEN_BUDGET", 2_000_000)
    if request_limit == 0 and token_limit == 0:
        return
    requests = max(0, requests)
    estimated_tokens = max(0, estimated_tokens)
    if (request_limit and requests > request_limit) or (
        token_limit and estimated_tokens > token_limit
    ):
        raise GlobalCostLimitExceeded("global_cost_limit_reached")

    conditions = []
    if request_limit:
        conditions.append(
            ChatGlobalUsageDaily.provider_request_units + requests <= request_limit
        )
    if token_limit:
        conditions.append(
            ChatGlobalUsageDaily.provider_token_units + estimated_tokens <= token_limit
        )
    stmt = (
        pg_insert(ChatGlobalUsageDaily)
        .values(
            usage_date=datetime.now(timezone.utc).date(),
            provider_request_units=requests,
            provider_token_units=estimated_tokens,
        )
        .on_conflict_do_update(
            index_elements=[ChatGlobalUsageDaily.usage_date],
            set_={
                "provider_request_units": (
                    ChatGlobalUsageDaily.provider_request_units + requests
                ),
                "provider_token_units": (
                    ChatGlobalUsageDaily.provider_token_units + estimated_tokens
                ),
                "updated_at": func.now(),
            },
            where=and_(*conditions),
        )
        .returning(ChatGlobalUsageDaily.provider_request_units)
    )
    async with get_session_factory()() as db:
        reserved = (await db.execute(stmt)).scalar_one_or_none()
        if reserved is None:
            await db.rollback()
            raise GlobalCostLimitExceeded("global_cost_limit_reached")
        await db.commit()
