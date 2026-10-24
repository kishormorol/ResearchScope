"""
Railway PostgreSQL storage layer.

Upserts papers into the Railway-hosted PostgreSQL database used by the
FastAPI backend.  Runs automatically at the end of the pipeline when
RAILWAY_DATABASE_URL is set.

The tsvector search_vector column is updated via a trigger that must be
created once:

    CREATE OR REPLACE FUNCTION papers_search_vector_update() RETURNS trigger AS $$
    BEGIN
        NEW.search_vector := to_tsvector('english',
            coalesce(NEW.title, '') || ' ' || coalesce(NEW.abstract, ''));
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER papers_search_vector_trigger
    BEFORE INSERT OR UPDATE ON papers
    FOR EACH ROW EXECUTE FUNCTION papers_search_vector_update();
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)

_BATCH = 100
_RETRY = [5, 15, 30]

_PAPER_COLS = {
    "id", "source", "source_type", "title", "abstract", "authors",
    "year", "published_date", "venue", "conference_rank", "paper_url",
    "pdf_url", "citations", "tags", "topics", "paper_score", "paper_type",
    "difficulty_level", "summary", "key_contribution", "why_it_matters",
    "one_line_takeaway", "fetched_at",
}

_LIST_COLS = {"authors", "tags", "topics"}


def _conn():
    url = os.environ.get("RAILWAY_DATABASE_URL", "").strip()
    if not url:
        return None
    try:
        import psycopg2
        return psycopg2.connect(url)
    except ImportError:
        log.warning("[railway] psycopg2 not installed — skipping Railway sync.")
        return None
    except Exception as exc:
        log.warning("[railway] connection failed: %s", exc)
        return None


def _paper_row(p: dict[str, Any]) -> dict[str, Any]:
    row = {k: p[k] for k in _PAPER_COLS if k in p}
    fetched_at = row.get("fetched_at")
    if isinstance(fetched_at, str) and not fetched_at.strip():
        row["fetched_at"] = None
    for col in _LIST_COLS:
        val = row.get(col)
        if isinstance(val, list):
            row[col] = json.dumps(val)
        elif val is None:
            row[col] = json.dumps([])
    # ensure year is int or None
    if "year" in row:
        try:
            row["year"] = int(row["year"]) if row["year"] else None
        except (TypeError, ValueError):
            row["year"] = None
    return row


def _upsert_papers(cur, rows: list[dict]) -> None:
    if not rows:
        return
    cols    = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(
        f"{c} = COALESCE(EXCLUDED.{c}, papers.{c})" if c == "fetched_at"
        else f"{c} = EXCLUDED.{c}"
        for c in cols if c != "id"
    )
    sql = (
        f"INSERT INTO papers ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}"
    )
    for i in range(0, len(rows), _BATCH):
        batch = rows[i: i + _BATCH]
        for attempt, delay in enumerate([0] + _RETRY):
            if delay:
                log.warning("[railway] retrying batch %d in %ds…", i, delay)
                time.sleep(delay)
            try:
                cur.executemany(sql, [list(r.values()) for r in batch])
                break
            except Exception as exc:
                if attempt < len(_RETRY):
                    continue
                raise
        log.info("[railway] upserted %d/%d papers", min(i + _BATCH, len(rows)), len(rows))


def load(source_type: str | None = None) -> list[dict] | None:
    """Read papers back from Railway — the complete, uncapped archive.

    Returns the rows as dicts (list columns decoded back to lists), optionally
    filtered to a single ``source_type`` ('journal' / 'conference'). Returns
    ``None`` when the DB is unreachable, so callers can distinguish "archive is
    empty" from "no complete source available" (and fall back to a full fetch
    rather than silently dropping the long tail).
    """
    conn = _conn()
    if conn is None:
        return None

    cols = sorted(_PAPER_COLS)
    sql  = f"SELECT {', '.join(cols)} FROM papers"
    params: list = []
    if source_type:
        sql += " WHERE source_type = %s"
        params.append(source_type)

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                fetched = cur.fetchall()
        out: list[dict] = []
        for row in fetched:
            d = dict(zip(cols, row))
            for c in _LIST_COLS:
                v = d.get(c)
                if isinstance(v, str):
                    try:
                        d[c] = json.loads(v)
                    except Exception:
                        d[c] = []
                elif v is None:
                    d[c] = []
            out.append(d)
        log.info(
            "[railway] loaded %d papers%s", len(out),
            f" (source_type={source_type})" if source_type else "",
        )
        return out
    except Exception as exc:
        log.warning("[railway] load failed: %s", exc)
        return None
    finally:
        conn.close()


def sync(papers: list[dict]) -> bool:
    conn = _conn()
    if conn is None:
        log.info("RAILWAY_DATABASE_URL not set — skipping Railway sync.")
        return False

    log.info("[railway] syncing %d papers …", len(papers))
    rows = [_paper_row(p) for p in papers if p.get("id")]

    try:
        with conn:
            with conn.cursor() as cur:
                _upsert_papers(cur, rows)
        log.info("[railway] sync complete.")
        return True
    except Exception as exc:
        log.error("[railway] sync failed: %s", exc)
        return False
    finally:
        conn.close()
