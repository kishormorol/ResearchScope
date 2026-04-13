"""Main pipeline for ResearchScope."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

from src.clustering.clusterer import TopicClusterer
from src.connectors.acl_connector import ACLAnthologyConnector
from src.connectors.arxiv_connector import ArxivConnector
from src.content.generator import ContentGenerator
from src.dedup.deduplicator import Deduplicator
from src.difficulty.assessor import DifficultyAssessor
from src.gaps.gap_extractor import GapExtractor
from src.normalization.schema import Author, Lab, Paper
from src.scoring.scorer import PaperScorer
from src.sitegen.generator import SiteGenerator
from src.tagging.tagger import PaperTagger


def _build_authors(papers: list[Paper]) -> list[Author]:
    """Aggregate per-author stats from papers."""
    author_map: dict[str, Author] = {}
    for paper in papers:
        for name in paper.authors:
            aid = re.sub(r"\s+", "_", name.lower())
            if aid not in author_map:
                author_map[aid] = Author(id=aid, name=name)
            author = author_map[aid]
            if paper.id not in author.paper_ids:
                author.paper_ids.append(paper.id)
            for tag in paper.tags:
                if tag not in author.top_topics:
                    author.top_topics.append(tag)

    # Simple momentum: papers in last 2 years / total papers
    current_year = datetime.now(timezone.utc).year
    for author in author_map.values():
        relevant = [
            p for p in papers
            if p.id in author.paper_ids and current_year - p.year <= 2
        ]
        total = len(author.paper_ids) or 1
        author.momentum_score = round(len(relevant) / total, 2)
        author.top_topics = author.top_topics[:5]

    return sorted(author_map.values(), key=lambda a: -len(a.paper_ids))


def _build_labs(papers: list[Paper]) -> list[Lab]:
    """Placeholder: universities are not reliably in the data for MVP."""
    return []


def run_pipeline(
    queries: list[str] | None = None,
    max_results_per_query: int = 50,
    output_dir: str = "data",
) -> dict:
    """Execute the full ResearchScope pipeline and return summary stats."""
    if queries is None:
        queries = [
            "machine learning",
            "natural language processing",
            "computer vision",
            "reinforcement learning",
        ]

    connectors = [ArxivConnector(), ACLAnthologyConnector()]
    all_papers: list[Paper] = []

    for connector in connectors:
        for query in queries:
            print(f"[pipeline] Fetching '{query}' from {connector.source_name} …")
            fetched = connector.fetch(query, max_results=max_results_per_query)
            print(f"[pipeline]   → {len(fetched)} papers")
            all_papers.extend(fetched)

    print(f"[pipeline] Total before dedup: {len(all_papers)}")

    deduplicator = Deduplicator()
    papers = deduplicator.deduplicate(all_papers)
    print(f"[pipeline] After dedup: {len(papers)}")

    scorer = PaperScorer()
    tagger = PaperTagger()
    assessor = DifficultyAssessor()
    content_gen = ContentGenerator()

    for paper in papers:
        paper = tagger.tag(paper)
        paper = assessor.assess(paper)
        paper = scorer.score(paper)
        paper.summary = content_gen.generate_summary(paper)
        paper.why_it_matters = content_gen.generate_why_it_matters(paper)

    papers.sort(key=lambda p: -p.read_first_score)

    authors = _build_authors(papers)
    clusterer = TopicClusterer()
    topics = clusterer.cluster(papers)
    gap_extractor = GapExtractor()
    gaps = gap_extractor.extract(papers)

    site_gen = SiteGenerator()
    site_gen.generate(papers, authors, topics, gaps, output_dir=output_dir)

    stats = {
        "total_papers": len(papers),
        "total_authors": len(authors),
        "total_topics": len(topics),
        "total_gaps": len(gaps),
    }
    print(f"[pipeline] Done. Stats: {stats}")
    return stats


if __name__ == "__main__":
    run_pipeline()
