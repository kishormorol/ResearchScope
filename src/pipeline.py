"""
ResearchScope — main pipeline.

Usage:
    python src/pipeline.py
    python src/pipeline.py --max-results 30 --output-dir data

The pipeline runs the following stages in order:
  1. Fetch   — connectors pull raw papers from sources
  2. Dedup   — remove near-duplicates
  3. Tag     — assign topic tags and paper_type
  4. Assess  — assign difficulty level
  5. Score   — compute all four score types
  6. Enrich  — generate content fields
  7. Cluster — group papers into topic clusters
  8. Gaps    — extract research gaps (3 layers)
  9. Aggregate — build author / lab / university objects
 10. Editorial — build daily editorial queue
 11. Site gen — write JSON for the static frontend
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Make "src" importable when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aggregation.aggregator import Aggregator
from src.clustering.clusterer import TopicClusterer
from src.connectors.acl_connector import ACLAnthologyConnector
from src.connectors.arxiv_connector import ArxivConnector
from src.connectors.cvf_connector import CVFConnector
from src.connectors.miniconf_connector import MiniconfConnector
from src.connectors.openalex_connector import OpenAlexConnector
from src.connectors.openreview_connector import OpenReviewConnector
from src.connectors.pmlr_connector import PMLRConnector
from src.connectors.semantic_scholar_connector import SemanticScholarConnector
from src.content.generator import ContentGenerator, EditorialQueue
from src.dedup.deduplicator import Deduplicator
from src.difficulty.assessor import DifficultyAssessor
from src.gaps.gap_extractor import GapExtractor
from src.normalization.schema import Paper
from src.scoring.scorer import PaperScorer
from src.sitegen.generator import SiteGenerator
from src.storage import railway_store
from src.tagging.tagger import PaperTagger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


# ── Affiliation enrichment via S2 batch lookup ───────────────────────────────

def _enrich_affiliations_from_s2(papers: list[Paper], batch_size: int = 500) -> None:
    """Batch-lookup arXiv papers on S2 to fill in affiliations_raw.

    Uses the S2 /paper/batch endpoint — one POST per 500 papers.
    Mutates papers in place; skips papers without an arXiv ID.
    """
    import json as _json
    import os
    import time
    import urllib.request

    key = os.getenv("SEMANTIC_SCHOLAR_KEY", "")
    headers = {
        "User-Agent":   "ResearchScope/1.0",
        "Content-Type": "application/json",
    }
    if key:
        headers["x-api-key"] = key

    # Build arXiv-ID → paper index
    id_map: dict[str, Paper] = {}
    for p in papers:
        arxiv_id = p.id.replace("arxiv:", "").split("v")[0]
        if arxiv_id:
            id_map[f"ArXiv:{arxiv_id}"] = p

    if not id_map:
        return

    ids = list(id_map.keys())
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        body = _json.dumps({"ids": chunk}).encode()
        url  = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=authors.name,authors.affiliations"
        req  = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                results = _json.loads(resp.read())
            for rec in results:
                if rec is None:
                    continue
                ext = (rec.get("externalIds") or {})
                arxiv_id = ext.get("ArXiv", "")
                paper = id_map.get(f"ArXiv:{arxiv_id}")
                if paper is None:
                    continue
                affiliations: list[str] = []
                for a in (rec.get("authors") or []):
                    for aff in (a.get("affiliations") or []):
                        aff_str = aff.strip() if isinstance(aff, str) else str(aff)
                        if aff_str and aff_str not in affiliations:
                            affiliations.append(aff_str)
                if affiliations:
                    paper.affiliations_raw = affiliations
        except Exception as exc:
            log.warning("  [s2] batch affiliation lookup failed (chunk %d): %s", i, exc)
        if i + batch_size < len(ids):
            time.sleep(0.5 if key else 2.0)


# ── Existing paper accumulation ───────────────────────────────────────────────

_SITE_DATA = Path(__file__).parent.parent / "site" / "data"

# Incremental journal-sync watermark: the date of the last successful journal
# fetch. Stored next to the data so it is committed alongside journals_db.json.
_JOURNAL_STATE = _SITE_DATA / "journal_sync_state.json"
# Re-scan this many days before the watermark so works OpenAlex indexes late
# (created_date trails publication) are not missed. Dedup absorbs any overlap.
_JOURNAL_LOOKBACK_DAYS = 7

# Venues treated as arXiv / unclassified (not conference proceedings)
_ARXIV_VENUES = {None, "", "arXiv", "Unknown"}


def _load_journal_watermark() -> str | None:
    """Return the YYYY-MM-DD created-date floor for an incremental fetch.

    The stored date is shifted back by ``_JOURNAL_LOOKBACK_DAYS``. Returns None
    when no prior sync is recorded, signalling a full backfill.
    """
    if not _JOURNAL_STATE.exists():
        return None
    try:
        with open(_JOURNAL_STATE, encoding="utf-8") as fh:
            last = json.load(fh).get("last_synced")
        floor = date.fromisoformat(last) - timedelta(days=_JOURNAL_LOOKBACK_DAYS)
        return floor.isoformat()
    except Exception as exc:
        log.warning("Could not read journal watermark (%s) — full fetch", exc)
        return None


def _save_journal_watermark() -> None:
    """Stamp today as the last successful journal sync."""
    try:
        _JOURNAL_STATE.parent.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).date().isoformat()
        with open(_JOURNAL_STATE, "w", encoding="utf-8") as fh:
            json.dump({"last_synced": today}, fh, indent=2)
        log.info("  [journals] watermark advanced → %s", today)
    except Exception as exc:
        log.warning("Could not write journal watermark: %s", exc)


def _load_complete_archive(source_type: str) -> list[Paper] | None:
    """Load the complete, uncapped archive for a source_type from Railway.

    Returns a list of Paper (possibly empty) when Railway answered, or None when
    it is unavailable — letting callers fall back to a full fetch rather than
    skipping work against an incomplete (capped JSON) view.
    """
    rows = railway_store.load(source_type=source_type)
    if rows is None:
        return None
    papers: list[Paper] = []
    for d in rows:
        try:
            papers.append(Paper.from_dict(d))
        except Exception:
            continue
    log.info("Loaded %d %s papers from Railway archive", len(papers), source_type)
    return papers


# A past block needs at least this many archived papers to count as settled.
# Any smaller and it was a partial fetch (keyword search, abstract cap, an API
# outage), and skipping it would freeze the gap forever: NeurIPS 2025 sat at
# 29 papers that way.
_SETTLED_MIN_PAPERS = 150


def _settled_conf_keys(papers: list[Paper],
                       min_papers: int = _SETTLED_MIN_PAPERS) -> set[str]:
    """Build the set of "<venue>:<year>" conference blocks safe to skip re-fetch.

    A block is settled when the complete archive already holds at least
    ``min_papers`` of its papers AND its year is in the past. The current
    calendar year is never skipped, so proceedings still being published keep
    getting refreshed each run.
    """
    cur_year = datetime.now(timezone.utc).year
    counts: dict[str, int] = {}
    for p in papers:
        if not p.venue or not p.year:
            continue
        try:
            year = int(p.year)
        except (TypeError, ValueError):
            continue
        if year < cur_year:
            key = f"{p.venue}:{year}"
            counts[key] = counts.get(key, 0) + 1
    # CONF_REFRESH_YEARS="2025,2026" forces those years to be fetched again
    force = {y.strip() for y in os.environ.get("CONF_REFRESH_YEARS", "").split(",") if y.strip()}
    return {key for key, n in counts.items()
            if n >= min_papers and key.rsplit(":", 1)[1] not in force}


def _is_conference_paper(p: Paper) -> bool:
    return p.venue not in _ARXIV_VENUES


def _load_arxiv_papers(max_age_days: int = 180) -> list[Paper]:
    """Load arXiv papers from papers_db.json, age-filtered to rolling window."""
    papers_file = _SITE_DATA / "papers_db.json"
    if not papers_file.exists():
        # First-ever run — fall back to legacy papers.json
        papers_file = _SITE_DATA / "papers.json"
    if not papers_file.exists():
        return []
    try:
        with open(papers_file, encoding="utf-8") as fh:
            raw = json.load(fh)
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max_age_days)
        ).strftime("%Y-%m-%d")
        all_existing = [Paper.from_dict(d) for d in raw]
        # Only keep arXiv papers within the rolling window
        kept = [
            p for p in all_existing
            if not _is_conference_paper(p)
            and (p.published_date or "9999-01-01") >= cutoff
        ]
        log.info(
            "Loaded %d arXiv papers from DB (%d within %d-day window)",
            len(all_existing), len(kept), max_age_days,
        )
        return kept
    except Exception as exc:
        log.warning("Could not load arXiv papers: %s", exc)
        return []


def _load_conference_papers() -> list[Paper]:
    """Load all conference papers from conferences_db.json — they never expire."""
    conf_file = _SITE_DATA / "conferences_db.json"
    if not conf_file.exists():
        return []
    try:
        with open(conf_file, encoding="utf-8") as fh:
            raw = json.load(fh)
        papers = [Paper.from_dict(d) for d in raw]
        log.info("Loaded %d conference papers from DB", len(papers))
        return papers
    except Exception as exc:
        log.warning("Could not load conference papers: %s", exc)
        return []


def _load_journal_papers() -> list[Paper]:
    """Load all journal papers from journals_db.json — they never expire."""
    journal_file = _SITE_DATA / "journals_db.json"
    if not journal_file.exists():
        return []
    try:
        with open(journal_file, encoding="utf-8") as fh:
            raw = json.load(fh)
        papers = [Paper.from_dict(d) for d in raw]
        log.info("Loaded %d journal papers from DB", len(papers))
        return papers
    except Exception as exc:
        log.warning("Could not load journal papers: %s", exc)
        return []


# ── Default queries ───────────────────────────────────────────────────────────

_DEFAULT_QUERIES = [
    "large language models",
    "natural language processing",
    "computer vision transformer",
    "reinforcement learning",
    "diffusion models",
    "retrieval augmented generation",
    "multimodal AI",
    "AI safety alignment",
    "code generation LLM",
]


# ── Pipeline ──────────────────────────────────────────────────────────────────

def _fetch_journal_papers(since: str | None = None) -> list[Paper]:
    """Bulk-fetch top CS journals via OpenAlex (keyless, systematic by source id).

    ``since`` (YYYY-MM-DD) restricts the fetch to works OpenAlex indexed on or
    after that date — the incremental path. It is only set when the complete
    journal archive is available to merge against, so the long tail is never
    dropped; otherwise a full backfill runs.

    OpenAlex is the primary source because the S2 journal search is unreliable
    here — it filters by venue *short name* and query text, which yields 0
    results and chronic HTTP 429/400s. S2 is only a non-fatal supplement when a
    key is configured, for venues OpenAlex under-indexes (e.g. JMLR/TMLR).
    Dedup later in the pipeline removes any overlap.
    """
    if since:
        log.info("  [openalex] incremental journal fetch (created since %s) …", since)
    else:
        log.info("  [openalex] full journal backfill …")
    journal_papers: list[Paper] = []
    fetch_ok = False
    try:
        journal_papers = OpenAlexConnector().fetch_journals(from_created_date=since)
        log.info("    → %d journal papers (openalex)", len(journal_papers))
        fetch_ok = True
    except Exception as exc:
        log.warning("  [openalex] journal fetch failed: %s", exc)

    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        log.info("  [s2] supplementing journals (JMLR/TMLR coverage) …")
        try:
            s2_journals = SemanticScholarConnector().fetch_journals()
            log.info("    → %d journal papers (s2)", len(s2_journals))
            journal_papers.extend(s2_journals)
        except Exception as exc:
            log.warning("  [s2] journal supplement failed: %s", exc)

    # Only advance the watermark when OpenAlex actually answered — a failed
    # fetch must not skip those papers on the next run.
    if fetch_ok:
        _save_journal_watermark()

    return journal_papers


def run_pipeline(
    queries: list[str] | None = None,
    max_results_per_query: int = 50,
    output_dir: str = "data",
    skip_acl: bool = False,
    today_mode: bool = False,
    today_max: int = 2000,
    skip_conferences: bool = False,
    conferences_only: bool = False,
    journals_only: bool = False,
    accumulate: bool = True,
    max_age_days: int = 180,
    backfill_from: str | None = None,
) -> dict:
    """Execute the full ResearchScope pipeline. Returns summary stats."""

    if queries is None:
        queries = _DEFAULT_QUERIES

    # ── Stage 1: Fetch ────────────────────────────────────────────────────────
    log.info("Stage 1/11 — Fetching papers …")
    arxiv = ArxivConnector()
    all_papers: list[Paper] = []

    # ── Incremental sync setup (conference / journal sync runs only) ───────────
    # The complete, uncapped archive lives in Railway. When it is reachable we
    # skip re-fetching settled work (immutable past proceedings / already-indexed
    # journal papers) and merge the skipped rows back from the archive. If Railway
    # is down we fall back to a full fetch so nothing below the JSON caps is lost.
    journal_archive: list[Paper] | None = None
    conf_archive:    list[Paper] | None = None
    journal_since:   str | None = None
    conf_skip_keys:  set[str] | None = None

    if journals_only or conferences_only:
        journal_archive = _load_complete_archive("journal")
        if journal_archive is not None:
            journal_since = _load_journal_watermark()
    if conferences_only:
        conf_archive = _load_complete_archive("conference")
        if conf_archive is not None:
            conf_skip_keys = _settled_conf_keys(conf_archive)
            log.info("  [conf-sync] %d settled venue/year blocks will be skipped",
                     len(conf_skip_keys))

    # ── Journals-only mode: fetch journal papers and skip every other source ──
    if journals_only:
        log.info("  journals-only mode: fetching journal papers only")
        all_papers.extend(_fetch_journal_papers(since=journal_since))

    # ── arXiv + ACL (skipped in conferences-only mode) ────────────────────────
    if conferences_only:
        log.info("  conferences-only mode: skipping arXiv and ACL")

    if backfill_from and not conferences_only and not journals_only:
        # ── Backfill mode: sweep entire date range from given date to today ──
        try:
            from_date = date.fromisoformat(backfill_from)
        except ValueError:
            log.error("--backfill-from must be YYYY-MM-DD, got: %s", backfill_from)
            return {}
        days = (date.today() - from_date).days
        log.info(
            "  [arxiv] backfill-mode: %s → today (%d days) …",
            backfill_from, days,
        )
        try:
            fetched = arxiv.fetch_range(from_date, max_results=50_000)
            log.info("    → %d papers", len(fetched))
            all_papers.extend(fetched)
        except Exception as exc:
            log.error("  [arxiv] fetch_range failed: %s", exc)
            return {}

    elif today_mode and not conferences_only and not journals_only:
        log.info("  [arxiv] today-mode: fetching all CS papers from last 2 days …")
        try:
            fetched = arxiv.fetch_today(max_results=today_max)
            log.info("    → %d papers", len(fetched))
            if fetched:
                all_papers.extend(fetched)
            else:
                log.warning("  [arxiv] fetch_today returned 0 papers — falling back to queries")
                today_mode = False
        except Exception as exc:
            log.warning("  [arxiv] fetch_today failed: %s — falling back to queries", exc)
            today_mode = False  # fall through to keyword queries

    if not today_mode and not backfill_from and not conferences_only and not journals_only:
        for query in queries:
            log.info("  [arxiv] '%s' …", query)
            try:
                fetched = arxiv.fetch(query, max_results=max_results_per_query)
            except Exception as exc:
                log.warning("  [arxiv] fetch failed for '%s': %s", query, exc)
                fetched = []
            log.info("    → %d papers", len(fetched))
            all_papers.extend(fetched)

    if not skip_acl and not conferences_only and not journals_only:
        acl = ACLAnthologyConnector()
        for query in queries:
            log.info("  [acl] '%s' …", query)
            try:
                fetched = acl.fetch(query, max_results=max_results_per_query)
            except Exception as exc:
                log.warning("  [acl] fetch failed for '%s': %s", query, exc)
                fetched = []
            log.info("    → %d papers", len(fetched))
            all_papers.extend(fetched)

    if (not skip_conferences or conferences_only) and not journals_only:
        if conferences_only:
            # ── Conference-sync mode: fetch ALL papers directly from proceedings ──
            # OpenReview — ICLR, NeurIPS, COLM (authenticates via env credentials)
            log.info("  [openreview] fetching ALL papers (ICLR 2022-26, NeurIPS 2022-25, ICML 2024-25, COLM 2024-26) …")
            try:
                fetched = OpenReviewConnector().fetch_all(skip_keys=conf_skip_keys)
                log.info("    → %d papers", len(fetched))
                all_papers.extend(fetched)
            except Exception as exc:
                log.warning("  [openreview] fetch_all failed: %s", exc)

            # Conference virtual sites — NeurIPS accepted papers without OpenReview,
            # whose API now challenges CI requests
            log.info("  [miniconf] fetching ALL papers (NeurIPS 2025-26) …")
            try:
                fetched = MiniconfConnector().fetch_all(skip_keys=conf_skip_keys)
                log.info("    → %d papers", len(fetched))
                all_papers.extend(fetched)
            except Exception as exc:
                log.warning("  [miniconf] fetch_all failed: %s", exc)

            log.info("  [pmlr] fetching ALL papers (ICML 2020-26, AISTATS 2021-26, UAI 2021-26) …")
            try:
                fetched = PMLRConnector().fetch_all(skip_keys=conf_skip_keys)
                log.info("    → %d papers", len(fetched))
                all_papers.extend(fetched)
            except Exception as exc:
                log.warning("  [pmlr] fetch_all failed: %s", exc)

            log.info("  [cvf] fetching ALL papers (CVPR 2021-26, ICCV 2021+23+25, ECCV 2020+22+24) …")
            try:
                fetched = CVFConnector().fetch_all(skip_keys=conf_skip_keys)
                log.info("    → %d papers", len(fetched))
                all_papers.extend(fetched)
            except Exception as exc:
                log.warning("  [cvf] fetch_all failed: %s", exc)

            log.info("  [acl] fetching ALL papers from anthology export (2020+) …")
            try:
                fetched = ACLAnthologyConnector().fetch_all(min_year=2020, skip_keys=conf_skip_keys)
                log.info("    → %d papers", len(fetched))
                all_papers.extend(fetched)
            except Exception as exc:
                log.warning("  [acl] fetch_all failed: %s", exc)

            # S2 bulk fetch — AAAI, IJCAI, KDD, WWW, SIGIR, WSDM, CHI, SIGMOD, ICSE
            log.info("  [s2] bulk-fetching AAAI, IJCAI, KDD, WWW, SIGIR, WSDM, CHI, SIGMOD, ICSE …")
            s2 = SemanticScholarConnector()
            try:
                fetched = s2.fetch_all(skip_keys=conf_skip_keys)
                log.info("    → %d papers", len(fetched))
                all_papers.extend(fetched)
            except Exception as exc:
                log.warning("  [s2] bulk fetch_all failed: %s", exc)

            all_papers.extend(_fetch_journal_papers(since=journal_since))

        else:
            # ── Keyword-query mode (used in daily pipeline if skip_conferences=False) ──
            conf_queries = queries[:4]
            for query in conf_queries:
                for connector, name in [
                    (OpenReviewConnector(), "openreview"),
                    (SemanticScholarConnector(venues=["AAAI","IJCAI","CHI","SIGMOD"]), "s2"),
                ]:
                    log.info("  [%s] '%s' …", name, query)
                    try:
                        fetched = connector.fetch(query, max_results=max_results_per_query)
                    except Exception as exc:
                        log.warning("  [%s] '%s' failed: %s", name, query, exc)
                        fetched = []
                    log.info("    → %d papers", len(fetched))
                    all_papers.extend(fetched)

    # ── OpenAlex (always, unless skip_conferences) ────────────────────────────
    if not skip_conferences and not journals_only:
        if conferences_only:
            if journal_since:
                log.info("  [openalex] incremental bulk-fetch ML/NLP/CV/IR (created since %s) …", journal_since)
            else:
                log.info("  [openalex] full bulk-fetch ML/NLP/CV/IR papers …")
            try:
                fetched = OpenAlexConnector(from_year=2022).fetch_all(from_created_date=journal_since)
                log.info("    → %d papers", len(fetched))
                all_papers.extend(fetched)
            except Exception as exc:
                log.warning("  [openalex] fetch_all failed: %s", exc)
        else:
            log.info("  [openalex] keyword search …")
            oa = OpenAlexConnector()
            for query in (queries or _DEFAULT_QUERIES)[:5]:
                try:
                    fetched = oa.fetch(query, max_results=max_results_per_query)
                    log.info("    [openalex] '%s' → %d", query, len(fetched))
                    all_papers.extend(fetched)
                except Exception as exc:
                    log.warning("  [openalex] '%s' failed: %s", query, exc)

    log.info("Fetched %d papers total (before dedup)", len(all_papers))

    if not all_papers:
        if today_mode and date.today().weekday() >= 5:
            log.info("No papers fetched — arXiv does not publish on weekends. Exiting cleanly.")
            return {"weekend_skip": True}
        log.error("No papers fetched. Check network connectivity.")
        return {}

    # ── Accumulate existing papers ────────────────────────────────────────────
    if accumulate:
        if conferences_only or journals_only:
            # Conference / journal sync: accumulate existing conference + journal
            # papers (no expiry) and also bring in arXiv papers so the site output
            # stays complete. In journals-only mode the freshly fetched journals
            # merge with these; conference/arXiv rows are preserved, not dropped.
            # Prefer the complete Railway archive (so skipped venue/years and the
            # journal long-tail are restored in full); fall back to capped JSON.
            existing_conf    = conf_archive if conf_archive is not None else _load_conference_papers()
            existing_journals = journal_archive if journal_archive is not None else _load_journal_papers()
            existing_arxiv   = _load_arxiv_papers(max_age_days=max_age_days)
            all_papers = all_papers + existing_conf + existing_journals + existing_arxiv
        else:
            # Daily arXiv run: accumulate existing arXiv (age-filtered)
            # and bring in conference + journal papers so they stay in the frontend output.
            existing_arxiv   = _load_arxiv_papers(max_age_days=max_age_days)
            existing_conf    = _load_conference_papers()
            existing_journals = _load_journal_papers()
            all_papers = all_papers + existing_arxiv + existing_conf + existing_journals
        log.info("Total with existing: %d papers", len(all_papers))

    # ── Stage 1b: Enrich arXiv papers with S2 affiliations ───────────────────
    arxiv_papers = [p for p in all_papers if p.source == "arxiv" and not p.affiliations_raw]
    if arxiv_papers:
        log.info("  [s2] enriching %d arXiv papers with affiliations …", len(arxiv_papers))
        try:
            _enrich_affiliations_from_s2(arxiv_papers)
            enriched = sum(1 for p in arxiv_papers if p.affiliations_raw)
            log.info("  [s2] affiliation data added to %d papers", enriched)
        except Exception as exc:
            log.warning("  [s2] affiliation enrichment failed: %s", exc)

    # ── Stage 2: Dedup ────────────────────────────────────────────────────────
    log.info("Stage 2/11 — Deduplicating …")
    deduplicator = Deduplicator()
    papers = deduplicator.deduplicate(all_papers)
    log.info("  %d papers after dedup", len(papers))

    # ── Stage 3: Tag ──────────────────────────────────────────────────────────
    log.info("Stage 3/11 — Tagging …")
    tagger = PaperTagger()
    for paper in papers:
        tagger.tag(paper)

    # ── Stage 4: Difficulty ────────────────────────────────────────────────────
    log.info("Stage 4/11 — Assessing difficulty …")
    assessor = DifficultyAssessor()
    for paper in papers:
        assessor.assess(paper)

    # ── Stage 5: Score ────────────────────────────────────────────────────────
    log.info("Stage 5/11 — Scoring …")
    scorer = PaperScorer()
    for paper in papers:
        scorer.score(paper)

    papers.sort(key=lambda p: -p.paper_score)

    # ── Stage 6: Content enrichment ───────────────────────────────────────────
    log.info("Stage 6/11 — Generating content …")
    content_gen = ContentGenerator()
    for paper in papers:
        content_gen.enrich(paper)

    # ── Stage 7: Topic clustering ─────────────────────────────────────────────
    log.info("Stage 7/11 — Clustering topics …")
    clusterer = TopicClusterer()
    topics = clusterer.cluster(papers)
    log.info("  %d topics", len(topics))

    # ── Stage 8: Research gaps ────────────────────────────────────────────────
    log.info("Stage 8/11 — Extracting research gaps …")
    gap_extractor = GapExtractor()
    gaps = gap_extractor.extract(papers)
    log.info("  %d gaps extracted", len(gaps))

    # ── Stage 9: Aggregate authors / labs / universities ─────────────────────
    log.info("Stage 9/11 — Aggregating authors, labs, universities …")
    aggregator = Aggregator()
    authors      = aggregator.build_authors(papers)
    labs         = aggregator.build_labs(papers)
    universities = aggregator.build_universities(papers)
    log.info(
        "  %d authors, %d labs, %d universities",
        len(authors), len(labs), len(universities),
    )

    # ── Stage 10: Editorial queue ──────────────────────────────────────────────
    log.info("Stage 10/11 — Building editorial queue …")
    editorial = EditorialQueue().build(papers, authors, labs, topics, gaps)

    # ── Stage 11: Site generation ──────────────────────────────────────────────
    log.info("Stage 11/11 — Writing site data to '%s/' …", output_dir)
    site_gen = SiteGenerator()
    site_gen.generate(
        papers=papers,
        authors=authors,
        topics=topics,
        gaps=gaps,
        output_dir=output_dir,
        labs=labs,
        universities=universities,
        editorial=editorial,
    )

    stats = {
        "total_papers":       len(papers),
        "total_authors":      len(authors),
        "total_labs":         len(labs),
        "total_universities": len(universities),
        "total_topics":       len(topics),
        "total_gaps":         len(gaps),
    }
    log.info("Pipeline complete. Stats: %s", stats)
    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ResearchScope pipeline — fetch, enrich, and publish CS research data."
    )
    parser.add_argument(
        "--max-results", type=int, default=50,
        help="Max papers per query per connector (default: 50, ignored in --today mode)",
    )
    parser.add_argument(
        "--output-dir", default="data",
        help="Directory to write JSON output (default: data/)",
    )
    parser.add_argument(
        "--skip-acl", action="store_true",
        help="Skip the ACL Anthology connector",
    )
    parser.add_argument(
        "--query", action="append", dest="queries",
        help="Override default queries (can be repeated)",
    )
    parser.add_argument(
        "--today", action="store_true",
        help="Fetch ALL papers submitted to arXiv in the last 2 days (ignores --max-results and --query for arXiv)",
    )
    parser.add_argument(
        "--today-max", type=int, default=2000,
        help="Max papers to fetch in --today mode (default: 2000)",
    )
    parser.add_argument(
        "--skip-conferences", action="store_true",
        help="Skip Semantic Scholar + OpenReview conference connectors",
    )
    parser.add_argument(
        "--conferences-only", action="store_true",
        help="Fetch ONLY from conference sources (S2 + OpenReview). Skip arXiv and ACL.",
    )
    parser.add_argument(
        "--journals-only", action="store_true",
        help="Fetch ONLY journal papers (OpenAlex by source id, +S2 supplement). "
             "Existing conference/arXiv papers are preserved (Railway upsert).",
    )
    parser.add_argument(
        "--backfill-from", metavar="YYYY-MM-DD",
        help="Fetch ALL arXiv CS papers from this date to today (e.g. 2026-01-01)",
    )
    parser.add_argument(
        "--fresh-start", action="store_true",
        help="Do not load existing papers.json — rebuild from scratch",
    )
    parser.add_argument(
        "--max-age-days", type=int, default=180,
        help="Rolling window in days for existing papers (default: 180)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    stats = run_pipeline(
        queries=args.queries,
        max_results_per_query=args.max_results,
        output_dir=args.output_dir,
        skip_acl=args.skip_acl,
        today_mode=args.today,
        today_max=args.today_max,
        skip_conferences=args.skip_conferences,
        conferences_only=args.conferences_only,
        journals_only=args.journals_only,
        accumulate=not args.fresh_start,
        max_age_days=args.max_age_days,
        backfill_from=args.backfill_from,
    )
    if not stats:
        sys.exit(1)
    if stats.get("weekend_skip"):
        sys.exit(0)
