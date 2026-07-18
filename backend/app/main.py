from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import auth, chat, favourites, paper_documents, papers, pipeline, search
from app.services.provider_service import chat_enabled, provider_configured

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from app.database import init_db
        await init_db()
    except Exception as exc:
        log.error("DB init failed (app still starting): %s", exc)
    yield


app = FastAPI(
    title="ResearchScope API",
    description="REST API for CS research papers, journals, conferences, authors, and more.",
    version="1.0.0",
    lifespan=lifespan,
)

# Restrict to known frontend origins. Set ALLOWED_ORIGINS on Railway to add
# additional origins (comma-separated), e.g. for local development.
_raw = os.environ.get(
    "ALLOWED_ORIGINS",
    "https://kishormorol.github.io",
)
_allowed_origins = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    allow_credentials=True,
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled error on %s: %s: %s", request.url.path, type(exc).__name__, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

app.include_router(papers.router)
app.include_router(paper_documents.router)
app.include_router(search.router)
app.include_router(auth.router)
app.include_router(favourites.router)
app.include_router(chat.router)
app.include_router(pipeline.router)


@app.get("/health")
async def health():
    db_url  = os.environ.get("DATABASE_URL", "")
    db_priv = os.environ.get("DATABASE_PRIVATE_URL", "")
    pg_host = os.environ.get("PGHOST", "")
    via     = "DATABASE_URL" if db_url else ("DATABASE_PRIVATE_URL" if db_priv else ("PGHOST" if pg_host else "none"))

    db_live = False
    try:
        from app.database import get_engine
        from sqlalchemy import text
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_live = True
    except Exception:
        pass

    return {
        "status": "ok", "db_configured": via != "none", "db_live": db_live,
        "via": via, "chat_enabled": chat_enabled(),
        "chat_provider_configured": provider_configured(),
    }


@app.get("/")
async def root():
    return {
        "name": "ResearchScope API",
        "docs": "/docs",
        "endpoints": [
            "/papers", "/search", "/auth", "/favourites", "/chat", "/pipeline"
        ],
    }
