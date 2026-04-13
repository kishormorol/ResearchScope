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
import logging
import sys
from pathlib import Path

# Make "src" importable when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aggregation.aggregator import Aggregator
from src.clustering.clusterer import TopicClusterer
from src.connectors.acl_connector import ACLAnthologyConnector
from src.connectors.arxiv_connector import ArxivConnector
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
) -> dict:
    """Execute the full ResearchScope pipeline. Returns summary stats."""

    if queries is None:
        queries = _DEFAULT_QUERIES

    # ── Stage 1: Fetch ────────────────────────────────────────────────────────
    log.info("Stage 1/11 — Fetching papers …")
    connectors = [ArxivConnector()]
    if not skip_acl:
        connectors.append(ACLAnthologyConnector())

    all_papers: list[Paper] = []
    for connector in connectors:
        for query in queries:
            log.info("  [%s] '%s' …", connector.source_name, query)
            try:
                fetched = connector.fetch(query, max_results=max_results_per_query)
            except Exception as exc:
                log.warning("  [%s] fetch failed for '%s': %s", connector.source_name, query, exc)
                fetched = []
            log.info("    → %d papers", len(fetched))
            all_papers.extend(fetched)

    log.info("Fetched %d papers total (before dedup)", len(all_papers))

    if not all_papers:
        log.error("No papers fetched. Check network connectivity.")
        return {}

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
        help="Max papers per query per connector (default: 50)",
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
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    stats = run_pipeline(
        queries=args.queries,
        max_results_per_query=args.max_results,
        output_dir=args.output_dir,
        skip_acl=args.skip_acl,
    )
    if not stats:
        sys.exit(1)
