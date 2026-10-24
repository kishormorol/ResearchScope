from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Paper
from app.schemas import PaperList, PaperOut
from app.services.paper_catalog_service import PaperCatalogError, get_or_import_paper

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get("", response_model=PaperList)
async def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: str | None = None,  # preprint | conference | journal
    venue: str | None = None,
    year: int | None = None,
    rank: str | None = None,  # A* | A | B
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Paper)
    if source_type:
        q = q.where(Paper.source_type == source_type)
    if venue:
        q = q.where(Paper.venue.ilike(f"%{venue}%"))
    if year:
        q = q.where(Paper.year == year)
    if rank:
        q = q.where(Paper.conference_rank == rank)
    if tag:
        q = q.where(Paper.tags.contains([tag]))

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar_one()

    q = (
        q.order_by(Paper.paper_score.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()

    return PaperList(total=total, page=page, page_size=page_size, results=rows)


@router.get("/conferences", response_model=PaperList)
async def list_conference_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    venue: str | None = None,
    year: int | None = None,
    rank: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Paper).where(Paper.source_type == "conference")
    if venue:
        q = q.where(Paper.venue.ilike(f"%{venue}%"))
    if year:
        q = q.where(Paper.year == year)
    if rank:
        q = q.where(Paper.conference_rank == rank)

    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                q.order_by(Paper.paper_score.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return PaperList(total=total, page=page, page_size=page_size, results=rows)


@router.get("/journals", response_model=PaperList)
async def list_journal_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    venue: str | None = None,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Paper).where(Paper.source_type == "journal")
    if venue:
        q = q.where(Paper.venue.ilike(f"%{venue}%"))
    if year:
        q = q.where(Paper.year == year)

    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                q.order_by(Paper.paper_score.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return PaperList(total=total, page=page, page_size=page_size, results=rows)


@router.get("/{paper_id}", response_model=PaperOut)
async def get_paper(paper_id: str, db: AsyncSession = Depends(get_db)):
    try:
        paper = await get_or_import_paper(db, paper_id)
    except PaperCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper
