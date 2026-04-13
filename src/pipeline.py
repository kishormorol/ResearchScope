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
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Make "src" importable when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aggregation.aggregator import Aggregator
from src.clustering.clusterer import TopicClusterer
from src.connectors.acl_connector import ACLAnthologyConnector
from src.connectors.arxiv_connector import ArxivConnector
from src.connectors.openreview_connector import OpenReviewConnector
from src.connectors.semantic_scholar_connector import SemanticScholarConnector
from src.content.generator import ContentGenerator, EditorialQueue
from src.dedup.deduplicator import Deduplicator
from src.difficulty.assessor import DifficultyAssessor
from src.gaps.gap_extractor import GapExtractor
from src.normalization.schema import Paper
from src.scoring.scorer import PaperScorer
from src.sitegen.generator import SiteGenerator
from src.tagging.tagger import PaperTagger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")


# ── Existing paper accumulation ───────────────────────────────────────────────

_SITE_DATA = Path(__file__).parent.parent / "site" / "data"


def _load_existing_papers(max_age_days: int = 180) -> list[Paper]:
    """Load previously collected papers from site/data/papers.json.

    Only returns papers within the rolling window so the dataset doesn't grow
    unboundedly.  New papers fetched this run take precedence in dedup.
    """
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
        kept = [
            p for p in all_existing
            if (p.published_date or "9999-01-01") >= cutoff
        ]
        log.info(
            "Loaded %d existing papers (%d within %d-day window)",
            len(all_existing), len(kept), max_age_days,
        )
        return kept
    except Exception as exc:
        log.warning("Could not load existing papers: %s", exc)
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

def run_pipeline(
    queries: list[str] | None = None,
    max_results_per_query: int = 50,
    output_dir: str = "data",
    skip_acl: bool = False,
    today_mode: bool = False,
    today_max: int = 2000,
    skip_conferences: bool = False,
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

    if backfill_from:
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

    elif today_mode:
        log.info("  [arxiv] today-mode: fetching all CS papers from last 2 days …")
        try:
            fetched = arxiv.fetch_today(max_results=today_max)
            log.info("    → %d papers", len(fetched))
            all_papers.extend(fetched)
        except Exception as exc:
            log.warning("  [arxiv] fetch_today failed: %s — falling back to queries", exc)
            today_mode = False  # fall through to keyword queries

    if not today_mode and not backfill_from:
        for query in queries:
            log.info("  [arxiv] '%s' …", query)
            try:
                fetched = arxiv.fetch(query, max_results=max_results_per_query)
            except Exception as exc:
                log.warning("  [arxiv] fetch failed for '%s': %s", query, exc)
                fetched = []
            log.info("    → %d papers", len(fetched))
            all_papers.extend(fetched)

    if not skip_acl:
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

    if not skip_conferences:
        # Semantic Scholar — ICLR, NeurIPS, ICML, AAAI, IJCAI, CVPR, ICCV, ECCV, CHI
        s2 = SemanticScholarConnector()
        conf_queries = queries[:4]  # use top 4 queries to keep runtime reasonable
        for query in conf_queries:
            log.info("  [s2-conferences] '%s' …", query)
            try:
                fetched = s2.fetch(query, max_results=max_results_per_query)
            except Exception as exc:
                log.warning("  [s2-conferences] fetch failed for '%s': %s", query, exc)
                fetched = []
            log.info("    → %d papers", len(fetched))
            all_papers.extend(fetched)

        # OpenReview — COLM
        or_conn = OpenReviewConnector()
        for query in conf_queries:
            log.info("  [openreview] '%s' …", query)
            try:
                fetched = or_conn.fetch(query, max_results=max_results_per_query)
            except Exception as exc:
                log.warning("  [openreview] fetch failed for '%s': %s", query, exc)
                fetched = []
            log.info("    → %d papers", len(fetched))
            all_papers.extend(fetched)

    log.info("Fetched %d papers total (before dedup)", len(all_papers))

    if not all_papers:
        log.error("No papers fetched. Check network connectivity.")
        return {}

    # ── Accumulate existing papers ────────────────────────────────────────────
    if accumulate:
        existing = _load_existing_papers(max_age_days=max_age_days)
        if existing:
            # New papers first — dedup keeps most complete, so freshly scored
            # versions of the same paper will naturally win if more complete.
            all_papers = all_papers + existing
            log.info("Total with existing: %d papers", len(all_papers))

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
        accumulate=not args.fresh_start,
        max_age_days=args.max_age_days,
        backfill_from=args.backfill_from,
    )
    if not stats:
        sys.exit(1)
