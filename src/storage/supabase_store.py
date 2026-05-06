"""
Supabase storage layer for ResearchScope.

Upserts all papers, authors, topics, gaps, and labs into Supabase so the
full dataset is available — no size caps, no rolling windows.

Usage (automatic via SiteGenerator when env vars are present):
    SUPABASE_URL=https://xxx.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=eyJ...
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_BATCH_SIZE = 500   # rows per upsert call (well within Supabase limits)


def _client():
    """Return a Supabase client, or None if env vars are missing."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        log.warning("supabase package not installed — skipping Supabase sync.")
        return None


def _upsert(client, table: str, rows: list[dict], conflict_col: str = "id") -> None:
    """Upsert rows in batches, logging progress."""
    total = len(rows)
    if not total:
        return
    for i in range(0, total, _BATCH_SIZE):
        batch = rows[i: i + _BATCH_SIZE]
        client.table(table).upsert(batch, on_conflict=conflict_col).execute()
        log.info("  %s: upserted %d/%d", table, min(i + _BATCH_SIZE, total), total)


def _paper_row(p: dict[str, Any]) -> dict[str, Any]:
    """Ensure all JSONB fields are proper Python objects (not strings)."""
    list_fields = {
        "authors", "author_ids", "affiliations_raw", "lab_ids", "university_ids",
        "topics", "tags", "prerequisites", "limitations", "future_work",
        "research_gap_signals",
    }
    dict_fields = {"score_breakdown"}
    row = dict(p)
    for f in list_fields:
        if isinstance(row.get(f), str):
            row[f] = []
    for f in dict_fields:
        if isinstance(row.get(f), str):
            row[f] = {}
    # remove computed-only properties that aren't real columns
    row.pop("url", None)
    row.pop("difficulty", None)
    return row


def sync(
    papers: list[dict],
    authors: list[dict] | None = None,
    topics: list[dict] | None = None,
    gaps: list[dict] | None = None,
    labs: list[dict] | None = None,
) -> bool:
    """
    Push all data to Supabase. Returns True if sync ran, False if skipped.

    Papers are upserted by `id` so re-running the pipeline is safe.
    """
    client = _client()
    if client is None:
        log.info("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping sync.")
        return False

    log.info("Syncing %d papers to Supabase…", len(papers))
    paper_rows = [_paper_row(p) for p in papers if p.get("id")]
    _upsert(client, "papers", paper_rows, conflict_col="id")

    if authors:
        log.info("Syncing %d authors…", len(authors))
        _upsert(client, "authors", authors, conflict_col="author_id")

    if topics:
        log.info("Syncing %d topics…", len(topics))
        _upsert(client, "topics", topics, conflict_col="id")

    if gaps:
        log.info("Syncing %d gaps…", len(gaps))
        _upsert(client, "gaps", gaps, conflict_col="gap_id")

    if labs:
        log.info("Syncing %d labs…", len(labs))
        _upsert(client, "labs", labs, conflict_col="lab_id")

    log.info("Supabase sync complete.")
    return True
