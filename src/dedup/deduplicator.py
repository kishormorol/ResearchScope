"""Deduplication logic for Paper objects."""
from __future__ import annotations

import re
import unicodedata

from src.normalization.schema import Paper


def _normalise_title(title: str) -> str:
    """Lowercase, strip punctuation and extra whitespace."""
    title = unicodedata.normalize("NFKC", title).lower()
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _completeness(paper: Paper) -> int:
    """Count how many optional fields are non-empty."""
    score = 0
    for value in (
        paper.abstract,
        paper.pdf_url,
        paper.summary,
        paper.why_it_matters,
    ):
        if value:
            score += 1
    score += len(paper.authors)
    score += len(paper.tags)
    score += len(paper.limitations)
    score += len(paper.future_work)
    if paper.citations:
        score += 1
    return score


def _similarity(a: str, b: str) -> float:
    """Simple Jaccard similarity on word sets."""
    wa = set(a.split())
    wb = set(b.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


class Deduplicator:
    """Remove near-duplicate papers from a list."""

    def __init__(self, threshold: float = 0.85) -> None:
        self.threshold = threshold

    def deduplicate(self, papers: list[Paper]) -> list[Paper]:
        """Return a deduplicated list, keeping the most complete entry."""
        normalised = [_normalise_title(p.title) for p in papers]
        kept: list[int] = []

        for i, paper in enumerate(papers):
            merged_into: int | None = None
            for j in kept:
                sim = _similarity(normalised[i], normalised[j])
                if sim >= self.threshold:
                    merged_into = j
                    break

            if merged_into is None:
                kept.append(i)
            else:
                # Replace kept entry if this one is more complete
                if _completeness(paper) > _completeness(papers[merged_into]):
                    kept[kept.index(merged_into)] = i

        return [papers[i] for i in kept]
