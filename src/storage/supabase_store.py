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
import time
from typing import Any

log = logging.getLogger(__name__)

_BATCH_SIZE = 100   # rows per upsert call — kept small to avoid statement timeouts on large tables
_RETRY_DELAYS = [5, 15, 30]  # seconds between retries on timeout

# Heavy content-generation columns not rendered anywhere in the frontend UI.
# Excluded from Supabase to stay within the 500 MB free-tier limit.
# The full data is preserved in site/data/*.json for static pages.
_PAPER_EXCLUDE_COLS: frozenset[str] = frozenset({
    "tweet_thread",
    "video_script_outline",
    "linkedin_post",
    "newsletter_blurb",
    "plain_english_explanation",
    "technical_summary",
    "score_breakdown",
    "content_hook",
    "biggest_caveat",
    "difficulty_reason",
    "affiliations_raw",   # raw string, superseded by author_ids
    "canonical_id",       # internal dedup field
    "cluster_id",         # internal clustering field
    "fetched_at",         # pipeline metadata, not used in UI
})


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
    """Upsert rows in batches with retries on statement timeout."""
    # Deduplicate by conflict key — Postgres rejects a batch that touches the same row twice
    seen: set = set()
    deduped = []
    for row in rows:
        key = row.get(conflict_col)
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    if len(deduped) < len(rows):
        log.warning("  %s: dropped %d duplicate rows before upsert", table, len(rows) - len(deduped))
    rows = deduped

    total = len(rows)
    if not total:
        return
    for i in range(0, total, _BATCH_SIZE):
        batch = rows[i: i + _BATCH_SIZE]
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                log.warning("  %s: timeout on batch %d/%d, retrying in %ds…", table, i, total, delay)
                time.sleep(delay)
            try:
                client.table(table).upsert(batch, on_conflict=conflict_col).execute()
                break
            except Exception as exc:
                if "57014" in str(exc) and attempt < len(_RETRY_DELAYS):
                    continue
                raise
        log.info("  %s: upserted %d/%d", table, min(i + _BATCH_SIZE, total), total)


def _paper_row(p: dict[str, Any]) -> dict[str, Any]:
    """Slim a paper dict for Supabase: fix JSONB types and drop excluded columns."""
    list_fields = {
        "authors", "author_ids", "lab_ids", "university_ids",
        "topics", "tags", "prerequisites", "limitations", "future_work",
        "research_gap_signals",
    }
    row = {k: v for k, v in p.items() if k not in _PAPER_EXCLUDE_COLS}
    for f in list_fields:
        if isinstance(row.get(f), str):
            row[f] = []
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
        author_rows = []
        for a in authors:
            row = {k: v for k, v in a.items() if k not in ("id", "top_topics")}
            if isinstance(row.get("paper_ids"), list):
                row["paper_ids"] = row["paper_ids"][:100]
            if isinstance(row.get("recent_paper_ids"), list):
                row["recent_paper_ids"] = row["recent_paper_ids"][:20]
            author_rows.append(row)
        _upsert(client, "authors", author_rows, conflict_col="author_id")

    if topics:
        log.info("Syncing %d topics…", len(topics))
        _upsert(client, "topics", topics, conflict_col="id")

    if gaps:
        log.info("Syncing %d gaps…", len(gaps))
        gap_rows = [{k: v for k, v in g.items() if k not in ("id", "source_paper_ids")} for g in gaps]
        _upsert(client, "gaps", gap_rows, conflict_col="gap_id")

    if labs:
        log.info("Syncing %d labs…", len(labs))
        lab_rows = [{k: v for k, v in l.items() if k not in ("id", "top_topics")} for l in labs]
        _upsert(client, "labs", lab_rows, conflict_col="lab_id")

    log.info("Supabase sync complete.")
    return True
