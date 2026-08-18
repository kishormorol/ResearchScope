"""
Snapshot the published-paper corpus that the benchmark is fitted against.

Papers are read from the live ResearchScope API rather than the capped
`site/data/*.json` exports: those are truncated for GitHub Pages (1k rows in
papers.json, 7.5k in the _db files) and would silently fit the reference
distributions to a small top-scored slice.

The snapshot is written as JSONL so a run can be resumed and so the fitted
references are reproducible from a frozen file — a requirement for the paper,
where "we fitted on the corpus as of <date>" has to mean something.

Note on venue filtering: the API's `venue` parameter is a SQL ILIKE substring
match, so `venue=NN` also returns TNNLS and `venue=CL` also returns TACL. We
therefore page the whole source_type and filter on exact venue locally.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

API_BASE = "https://researchscope-production.up.railway.app"
PAGE_SIZE = 100          # API caps page_size at 100
_MAX_RETRIES = 4
_BACKOFF_SECONDS = 2.0

# Fields we keep. The API returns derived scores too, but the benchmark must
# not be fitted on ResearchScope's own paper_score — that would make the
# reference distributions a function of our scorer rather than of the corpus.
KEEP_FIELDS = (
    "id", "source", "source_type", "title", "abstract", "authors", "year",
    "published_date", "venue", "conference_rank", "paper_url", "pdf_url",
    "citations",
)


def _get(path: str) -> dict:
    last: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(f"{API_BASE}{path}", timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            wait = _BACKOFF_SECONDS * (2 ** attempt)
            log.warning("GET %s failed (%s); retry in %.0fs", path, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"GET {path} failed after {_MAX_RETRIES} attempts") from last


def total_papers(source_type: str = "journals") -> int:
    return _get(f"/papers/{source_type}?page_size=1")["total"]


def iter_papers(source_type: str = "journals",
                start_page: int = 1,
                max_pages: int | None = None) -> Iterator[dict]:
    """Yield papers page by page, trimmed to KEEP_FIELDS."""
    page = start_page
    seen_pages = 0
    while True:
        if max_pages is not None and seen_pages >= max_pages:
            return
        payload = _get(f"/papers/{source_type}?page={page}&page_size={PAGE_SIZE}")
        rows = payload.get("results") or []
        if not rows:
            return
        for row in rows:
            yield {k: row.get(k) for k in KEEP_FIELDS}
        page += 1
        seen_pages += 1


def snapshot(out_path: Path,
             source_type: str = "journals",
             max_pages: int | None = None,
             resume: bool = True) -> int:
    """Write the corpus to JSONL. Returns the number of rows written.

    With `resume`, an existing file is kept and paging restarts at the page
    after the last complete one, so an interrupted 764-page pull continues
    instead of starting over.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = 0
    if resume and out_path.exists():
        with out_path.open() as fh:
            existing = sum(1 for _ in fh)
    start_page = existing // PAGE_SIZE + 1
    if existing:
        log.info("resuming: %d rows present, restarting at page %d",
                 existing, start_page)
        # Drop a partial trailing page so pagination stays aligned.
        keep = (start_page - 1) * PAGE_SIZE
        if existing != keep:
            lines = out_path.read_text().splitlines()[:keep]
            out_path.write_text("\n".join(lines) + ("\n" if lines else ""))
            existing = keep

    written = existing
    with out_path.open("a") as fh:
        for paper in iter_papers(source_type, start_page, max_pages):
            fh.write(json.dumps(paper, ensure_ascii=False) + "\n")
            written += 1
            if written % 2000 == 0:
                log.info("  %d rows", written)
    return written


def load(path: Path, venue: str | None = None) -> list[dict]:
    """Read a snapshot back, optionally filtering to one exact venue."""
    rows: list[dict] = []
    with path.open() as fh:
        for line in fh:
            row = json.loads(line)
            if venue is None or row.get("venue") == venue:
                rows.append(row)
    return rows
