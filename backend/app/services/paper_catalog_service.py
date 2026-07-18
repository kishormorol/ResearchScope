from __future__ import annotations

import os
from urllib.parse import quote

import httpx
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper
from app.schemas import PaperOut

_MAX_METADATA_BYTES = 1_000_000


class PaperCatalogError(RuntimeError):
    def __init__(self, code: str, status_code: int = 502):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def catalog_fallback_url() -> str | None:
    value = os.environ.get("PAPER_CATALOG_FALLBACK_URL", "").strip().rstrip("/")
    return value or None


async def fetch_catalog_paper(
    paper_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict | None:
    """Fetch and validate one paper from the configured trusted metadata catalog."""
    base_url = catalog_fallback_url()
    if not base_url:
        return None

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10, follow_redirects=False)

    try:
        response = await client.get(f"{base_url}/papers/{quote(paper_id, safe='')}")
    except httpx.HTTPError as exc:
        raise PaperCatalogError("paper_catalog_unavailable") from exc
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise PaperCatalogError("paper_catalog_unavailable")
    if len(response.content) > _MAX_METADATA_BYTES:
        raise PaperCatalogError("paper_catalog_response_too_large")

    try:
        paper = PaperOut.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise PaperCatalogError("paper_catalog_invalid_response") from exc
    if paper.id != paper_id:
        raise PaperCatalogError("paper_catalog_id_mismatch")
    return paper.model_dump()


async def get_or_import_paper(db: AsyncSession, paper_id: str) -> Paper | None:
    """Return a local paper, importing trusted metadata on a local cache miss."""
    paper = await db.get(Paper, paper_id)
    if paper:
        return paper

    payload = await fetch_catalog_paper(paper_id)
    if payload is None:
        return None

    statement = (
        pg_insert(Paper)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=[Paper.id])
    )
    await db.execute(statement)
    await db.commit()
    return await db.get(Paper, paper_id)
