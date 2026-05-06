"""
One-time migration: push all existing ResearchScope JSON data to Supabase.

Usage:
    pip install supabase
    export SUPABASE_URL=https://ippobommkdtemzfcmqic.supabase.co
    export SUPABASE_SERVICE_ROLE_KEY=<your service_role key>
    python scripts/migrate_to_supabase.py

What it migrates:
    papers_db.json      → papers table  (full arXiv papers)
    conferences_db.json → papers table  (conference papers)
    authors.json        → authors table
    topics.json         → topics table
    gaps.json           → gaps table
    labs.json           → labs table
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

REPO_ROOT  = Path(__file__).parent.parent
DATA_DIR   = REPO_ROOT / "site" / "data"
BATCH_SIZE = 500


# ── Supabase client ────────────────────────────────────────────────────────────

def get_client():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        log.error("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY before running.")
        sys.exit(1)
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        log.error("Run: pip install supabase")
        sys.exit(1)


# ── Helpers ────────────────────────────────────────────────────────────────────

def load(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        log.warning("%s not found — skipping.", filename)
        return []
    log.info("Loading %s …", filename)
    data = json.loads(path.read_text(encoding="utf-8"))
    # some files are dicts (editorial, stats) — skip those
    if isinstance(data, list):
        return data
    return []


def upsert(client, table: str, rows: list[dict], conflict_col: str = "id") -> None:
    total = len(rows)
    if not total:
        log.info("  %s: nothing to upsert.", table)
        return
    ok = 0
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        try:
            client.table(table).upsert(batch, on_conflict=conflict_col).execute()
            ok += len(batch)
            log.info("  %s  %d / %d", table.ljust(10), ok, total)
        except Exception as e:
            log.error("  %s batch %d-%d failed: %s", table, i, i + len(batch), e)
            # retry row by row so one bad record doesn't block the rest
            for row in batch:
                try:
                    client.table(table).upsert([row], on_conflict=conflict_col).execute()
                    ok += 1
                except Exception as row_err:
                    log.error("    skipping row %s: %s", row.get(conflict_col, "?"), row_err)
    log.info("  %s: done (%d/%d rows).", table, ok, total)


def clean_paper(p: dict) -> dict | None:
    """Drop computed-only properties; ensure id is present."""
    if not p.get("id"):
        return None
    row = dict(p)
    row.pop("url", None)
    row.pop("difficulty", None)
    # ensure JSONB fields are lists/dicts, not strings
    for f in ("authors", "author_ids", "affiliations_raw", "lab_ids",
              "university_ids", "topics", "tags", "prerequisites",
              "limitations", "future_work", "research_gap_signals"):
        if not isinstance(row.get(f), list):
            row[f] = []
    if not isinstance(row.get("score_breakdown"), dict):
        row["score_breakdown"] = {}
    return row


def clean_author(a: dict) -> dict | None:
    if not a.get("author_id"):
        return None
    row = dict(a)
    row.pop("id", None)          # computed alias
    row.pop("top_topics", None)  # computed alias
    row.pop("paper_count", None) # computed by _slim_author, not a real column
    for f in ("aliases", "affiliations", "paper_ids", "recent_paper_ids",
              "topics", "lab_ids", "university_ids"):
        if not isinstance(row.get(f), list):
            row[f] = []
    if not isinstance(row.get("momentum_breakdown"), dict):
        row["momentum_breakdown"] = {}
    if not isinstance(row.get("conference_counts"), dict):
        row["conference_counts"] = {}
    return row


def clean_topic(t: dict) -> dict | None:
    if not t.get("id"):
        return None
    row = dict(t)
    for f in ("keywords", "paper_ids", "starter_pack_ids",
              "frontier_pack_ids", "prerequisites", "related_topics"):
        if not isinstance(row.get(f), list):
            row[f] = []
    return row


def clean_gap(g: dict) -> dict | None:
    row = dict(g)
    # normalise gap_id
    if not row.get("gap_id"):
        row["gap_id"] = row.get("id", "")
    if not row["gap_id"]:
        return None
    row.pop("id", None)
    row.pop("source_paper_ids", None)
    for f in ("evidence_paper_ids", "suggested_projects"):
        if not isinstance(row.get(f), list):
            row[f] = []
    return row


def clean_lab(l: dict) -> dict | None:
    if not l.get("lab_id"):
        return None
    row = dict(l)
    row.pop("id", None)
    row.pop("top_topics", None)
    for f in ("aliases", "authors", "paper_ids", "recent_papers", "topics"):
        if not isinstance(row.get(f), list):
            row[f] = []
    return row


def _dedup(rows: list[dict], key: str) -> list[dict]:
    """Remove duplicate rows by key, keeping the last occurrence."""
    seen: dict[str, dict] = {}
    for r in rows:
        k = r.get(key)
        if k:
            seen[k] = r
    return list(seen.values())


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    client = get_client()

    # ── Papers (arXiv + conferences combined into one table) ──────────────────
    arxiv_raw   = load("papers_db.json")
    conf_raw    = load("conferences_db.json")
    all_papers  = arxiv_raw + conf_raw
    # deduplicate by id (conferences_db may overlap with papers_db for some venues)
    seen: set[str] = set()
    papers: list[dict] = []
    for p in all_papers:
        pid = p.get("id", "")
        if pid and pid not in seen:
            cleaned = clean_paper(p)
            if cleaned:
                papers.append(cleaned)
                seen.add(pid)
    log.info("Total unique papers to upsert: %d  (arXiv: %d, conference: %d)",
             len(papers), len(arxiv_raw), len(conf_raw))
    upsert(client, "papers", papers, conflict_col="id")

    # ── Authors ───────────────────────────────────────────────────────────────
    authors = _dedup(
        [r for r in (clean_author(a) for a in load("authors.json")) if r],
        key="author_id",
    )
    upsert(client, "authors", authors, conflict_col="author_id")

    # ── Topics ────────────────────────────────────────────────────────────────
    topics = _dedup(
        [r for r in (clean_topic(t) for t in load("topics.json")) if r],
        key="id",
    )
    upsert(client, "topics", topics, conflict_col="id")

    # ── Gaps ──────────────────────────────────────────────────────────────────
    gaps = _dedup(
        [r for r in (clean_gap(g) for g in load("gaps.json")) if r],
        key="gap_id",
    )
    upsert(client, "gaps", gaps, conflict_col="gap_id")

    # ── Labs ──────────────────────────────────────────────────────────────────
    labs = _dedup(
        [r for r in (clean_lab(l) for l in load("labs.json")) if r],
        key="lab_id",
    )
    upsert(client, "labs", labs, conflict_col="lab_id")

    log.info("Migration complete!")


if __name__ == "__main__":
    main()
