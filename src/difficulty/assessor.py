"""Difficulty assessment for papers."""
from __future__ import annotations

import re

from src.normalization.schema import Paper

_BEGINNER_TAGS = {"Sentiment Analysis", "Summarization", "QA", "Translation"}
_ADVANCED_PATTERNS = re.compile(
    r"theorem|proof|lemma|corollary|variational|bayesian|stochastic|"
    r"convergence|gradient descent|manifold|topology|eigenvalue|"
    r"novel architecture|architecture search|nas\b|causal|"
    r"adversarial training|generative adversarial|vae\b",
    re.IGNORECASE,
)
_BEGINNER_PATTERNS = re.compile(
    r"survey|overview|tutorial|introduction to|beginners|primer|"
    r"getting started|hands.on",
    re.IGNORECASE,
)


class DifficultyAssessor:
    """Assign a difficulty level (beginner / intermediate / advanced) to a paper."""

    def assess(self, paper: Paper) -> Paper:
        text = f"{paper.title} {paper.abstract}"

        if _BEGINNER_PATTERNS.search(text):
            paper.difficulty = "beginner"
            return paper

        tag_set = set(paper.tags)
        if tag_set & _BEGINNER_TAGS and not _ADVANCED_PATTERNS.search(text):
            paper.difficulty = "beginner"
            return paper

        if _ADVANCED_PATTERNS.search(text):
            paper.difficulty = "advanced"
            return paper

        paper.difficulty = "intermediate"
        return paper
