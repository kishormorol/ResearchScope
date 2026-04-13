"""Research gap detection utilities."""

from __future__ import annotations

from collections import Counter

from researchscope.models.paper import Paper


def find_research_gaps(
    papers: list[Paper],
    min_keyword_freq: int = 2,
    top_n: int = 10,
) -> list[str]:
    """Identify potential research gaps from a collection of papers.

    The current implementation uses a lightweight keyword co-occurrence
    heuristic: keywords that appear in very few papers relative to the
    corpus size are surfaced as under-explored topics.

    Args:
        papers: Collection of papers to analyse.
        min_keyword_freq: Minimum number of occurrences for a keyword to be
            included in the analysis (filters noise).
        top_n: Number of gap topics to return.

    Returns:
        List of keyword strings that represent potential research gaps,
        ordered from least to most common (most under-explored first).
    """
    if not papers:
        return []

    keyword_counts: Counter[str] = Counter()
    for paper in papers:
        for kw in paper.keywords:
            if kw:
                keyword_counts[kw.lower()] += 1

    # Retain only keywords that appear at least min_keyword_freq times
    # to avoid surfacing single-paper noise.
    filtered = {
        kw: cnt for kw, cnt in keyword_counts.items() if cnt >= min_keyword_freq
    }

    if not filtered:
        return []

    # The "gaps" are the least-covered topics that still have meaningful
    # representation in the corpus.
    least_covered = sorted(filtered, key=lambda kw: filtered[kw])
    return least_covered[:top_n]
