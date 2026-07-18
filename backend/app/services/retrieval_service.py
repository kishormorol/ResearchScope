from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PaperChunk


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    chunk_index: int
    page_start: int
    page_end: int
    section: str | None
    content: str
    parent_chunk_index: int | None = None
    content_type: str = "paragraph"
    token_count: int = 0


def _to_result(chunk: PaperChunk) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk.id,
        chunk_index=chunk.chunk_index,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        section=chunk.section,
        content=chunk.content,
        parent_chunk_index=chunk.parent_chunk_index,
        content_type=chunk.content_type or "paragraph",
        token_count=chunk.token_count or max(1, len(chunk.content) // 4),
    )


def classify_query(question: str) -> str:
    normalized = " ".join(question.lower().split())
    if re.search(
        r"\b(figure|fig\.?|table|chart|diagram|plot|graph|equation)\b", normalized
    ):
        return "visual"
    if re.search(
        r"\b(summarize|summary|overview|whole paper|entire paper|main contribution|"
        r"key contributions|explain this paper|what is this paper about)\b",
        normalized,
    ):
        return "global"
    return "local"


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    dot = math.fsum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(math.fsum(value * value for value in left))
    right_norm = math.sqrt(math.fsum(value * value for value in right))
    if not left_norm or not right_norm:
        return -1.0
    return dot / (left_norm * right_norm)


def _embedding_literal(
    values: list[float], *, pgvector: bool
) -> str | list[float]:
    normalized = [float(value) for value in values]
    if not all(math.isfinite(value) for value in normalized):
        raise ValueError("embedding values must be finite")
    if pgvector:
        return json.dumps(normalized, allow_nan=False, separators=(",", ":"))
    return normalized


def _semantic_search_statement(
    *, dimensions: int, pgvector: bool, filter_model: bool
):
    model_filter = "AND pc.embedding_model = :embedding_model" if filter_model else ""
    if pgvector:
        vector_type = f"vector({dimensions})" if dimensions == 256 else "vector"
        distance = (
            f"(pc.embedding::{vector_type}) <=> "
            f"CAST(:query_embedding AS {vector_type})"
        )
        sql = f"""
            SELECT pc.*
            FROM paper_chunks AS pc
            WHERE pc.paper_id = :paper_id
              AND pc.content_type != 'parent'
              AND pc.embedding IS NOT NULL
              AND array_length(pc.embedding, 1) = :dimensions
              {model_filter}
            ORDER BY {distance}, pc.id
            LIMIT :semantic_limit
        """
    else:
        sql = f"""
            SELECT pc.*
            FROM paper_chunks AS pc
            CROSS JOIN LATERAL (
                SELECT
                    SUM(pair.chunk_value * pair.query_value) /
                    NULLIF(
                        SQRT(SUM(pair.chunk_value * pair.chunk_value)) *
                        SQRT(SUM(pair.query_value * pair.query_value)),
                        0
                    ) AS score
                FROM unnest(
                    pc.embedding,
                    CAST(:query_embedding AS REAL[])
                ) AS pair(chunk_value, query_value)
            ) AS similarity
            WHERE pc.paper_id = :paper_id
              AND pc.content_type != 'parent'
              AND pc.embedding IS NOT NULL
              AND array_length(pc.embedding, 1) = :dimensions
              {model_filter}
            ORDER BY similarity.score DESC NULLS LAST, pc.id
            LIMIT :semantic_limit
        """
    return select(PaperChunk).from_statement(text(sql))


async def _pgvector_available(db: AsyncSession) -> bool:
    return bool(
        (
            await db.execute(text("SELECT to_regtype('vector') IS NOT NULL"))
        ).scalar_one()
    )


def reciprocal_rank_fusion(
    rankings: list[list[int]], *, constant: int = 60
) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for position, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (constant + position)
    return scores


def _section_bonus(query: str, section: str | None) -> float:
    if not section:
        return 0.0
    query = query.lower()
    section = section.lower()
    aliases = {
        "method": ("method", "methodology", "approach", "architecture"),
        "result": ("result", "evaluation", "experiment", "performance"),
        "limitation": ("limitation", "weakness", "failure", "future work"),
        "conclusion": ("conclusion", "takeaway", "contribution"),
    }
    for intent, words in aliases.items():
        if any(word in query for word in words) and intent in section:
            return 0.015
    return 0.0


async def retrieve_full_context(
    db: AsyncSession, paper_id: str, *, max_tokens: int
) -> list[RetrievedChunk]:
    rows = list(
        (
            await db.execute(
                select(PaperChunk)
                .where(
                    PaperChunk.paper_id == paper_id,
                    PaperChunk.content_type == "parent",
                )
                .order_by(PaperChunk.chunk_index)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        rows = list(
            (
                await db.execute(
                    select(PaperChunk)
                    .where(PaperChunk.paper_id == paper_id)
                    .order_by(PaperChunk.chunk_index)
                )
            )
            .scalars()
            .all()
        )

    selected: list[RetrievedChunk] = []
    used = 0
    for row in rows:
        result = _to_result(row)
        tokens = result.token_count or max(1, len(result.content) // 4)
        if selected and used + tokens > max_tokens:
            break
        selected.append(result)
        used += tokens
    return selected


async def retrieve_chunks(
    db: AsyncSession,
    paper_id: str,
    query: str,
    *,
    query_embedding: list[float] | None = None,
    query_embedding_model: str | None = None,
    limit: int = 10,
) -> list[RetrievedChunk]:
    lexical_limit = max(limit, int(os.environ.get("CHAT_LEXICAL_CANDIDATES", "20")))
    semantic_limit = max(limit, int(os.environ.get("CHAT_SEMANTIC_CANDIDATES", "20")))
    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(PaperChunk.search_vector, tsquery)
    lexical = list(
        (
            await db.execute(
                select(PaperChunk)
                .where(
                    PaperChunk.paper_id == paper_id,
                    PaperChunk.content_type != "parent",
                    PaperChunk.search_vector.op("@@")(tsquery),
                )
                .order_by(rank.desc(), PaperChunk.chunk_index)
                .limit(lexical_limit)
            )
        )
        .scalars()
        .all()
    )

    semantic: list[PaperChunk] = []
    if query_embedding:
        use_pgvector = await _pgvector_available(db)
        semantic_stmt = _semantic_search_statement(
            dimensions=len(query_embedding),
            pgvector=use_pgvector,
            filter_model=bool(query_embedding_model),
        )
        parameters = {
            "paper_id": paper_id,
            "dimensions": len(query_embedding),
            "query_embedding": _embedding_literal(
                query_embedding, pgvector=use_pgvector
            ),
            "semantic_limit": semantic_limit,
        }
        if query_embedding_model:
            parameters["embedding_model"] = query_embedding_model
        semantic = list(
            (await db.execute(semantic_stmt, parameters)).scalars().all()
        )

    rows_by_id: dict[int, PaperChunk] = {}
    for row in lexical + semantic:
        rows_by_id[row.id] = row
    scores = reciprocal_rank_fusion(
        [[row.id for row in lexical], [row.id for row in semantic]]
    )
    for row_id, row in rows_by_id.items():
        scores[row_id] += _section_bonus(query, row.section)

    if not scores:
        fallback = list(
            (
                await db.execute(
                    select(PaperChunk)
                    .where(
                        PaperChunk.paper_id == paper_id,
                        PaperChunk.content_type != "parent",
                    )
                    .order_by(PaperChunk.chunk_index)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [_to_result(chunk) for chunk in fallback]

    ranked = sorted(scores, key=lambda row_id: (-scores[row_id], row_id))
    seed_count = max(1, min(len(ranked), min(8, max(4, limit - 2))))
    seeds = [rows_by_id[row_id] for row_id in ranked[:seed_count]]
    selected: list[PaperChunk] = list(seeds)
    selected_ids = {row.id for row in selected}

    parent_indexes = {
        row.parent_chunk_index
        for row in seeds[:2]
        if row.parent_chunk_index is not None
    }
    if parent_indexes:
        parents = list(
            (
                await db.execute(
                    select(PaperChunk)
                    .where(
                        PaperChunk.paper_id == paper_id,
                        PaperChunk.chunk_index.in_(parent_indexes),
                    )
                    .order_by(PaperChunk.chunk_index)
                )
            )
            .scalars()
            .all()
        )
        for row in parents:
            if len(selected) >= limit:
                break
            if row.id not in selected_ids:
                selected.append(row)
                selected_ids.add(row.id)

    if len(selected) < limit:
        neighbor_indexes = {
            index
            for row in seeds[:3]
            for index in (row.chunk_index - 1, row.chunk_index + 1)
            if index >= 0
        }
        neighbors = list(
            (
                await db.execute(
                    select(PaperChunk)
                    .where(
                        PaperChunk.paper_id == paper_id,
                        PaperChunk.content_type != "parent",
                        PaperChunk.chunk_index.in_(neighbor_indexes),
                    )
                    .order_by(PaperChunk.chunk_index)
                )
            )
            .scalars()
            .all()
        )
        for row in neighbors:
            if len(selected) >= limit:
                break
            if row.id not in selected_ids:
                selected.append(row)
                selected_ids.add(row.id)

    return [_to_result(chunk) for chunk in selected[:limit]]
