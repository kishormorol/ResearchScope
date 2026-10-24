from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

log = logging.getLogger(__name__)

def _database_url() -> str:
    """
    Resolve the database URL from environment variables.
    Railway may inject the connection as DATABASE_URL, DATABASE_PRIVATE_URL,
    or as individual PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE variables.
    """
    # 1. Standard DATABASE_URL
    for key in ("DATABASE_URL", "DATABASE_PRIVATE_URL", "DATABASE_PUBLIC_URL"):
        url = os.environ.get(key, "").strip()
        if url:
            log.info("Using database URL from %s", key)
            return url.replace("postgresql://", "postgresql+asyncpg://")

    # 2. Individual PG* variables (Railway injects these too)
    host = os.environ.get("PGHOST", "").strip()
    if host:
        port = os.environ.get("PGPORT", "5432").strip()
        user = os.environ.get("PGUSER", "postgres").strip()
        password = os.environ.get("PGPASSWORD", "").strip()
        dbname = os.environ.get("PGDATABASE", "railway").strip()
        url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"
        log.info(
            "Using database URL built from PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE"
        )
        return url

    raise RuntimeError(
        "No database connection found. Set DATABASE_URL or the "
        "PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE variables."
    )


def _ssl_mode(url: str) -> str:
    # Local connections don't have SSL; Railway's public proxy requires it.
    if any(h in url for h in ("localhost", "127.0.0.1", "[::1]")):
        return "disable"
    return os.environ.get("DATABASE_SSL", "require")


def _make_engine():
    url = _database_url()
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={"ssl": _ssl_mode(url)},
    )


_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


class Base(DeclarativeBase):
    pass


async def get_db():
    async with get_session_factory()() as session:
        yield session


async def init_db() -> None:
    try:
        from sqlalchemy import text

        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Idempotent migration: add notes column if not present
            await conn.execute(
                text("ALTER TABLE favourites ADD COLUMN IF NOT EXISTS notes TEXT")
            )
        log.info("Database tables initialised.")
    except Exception as exc:
        log.error("Database init failed: %s", exc)
        raise
