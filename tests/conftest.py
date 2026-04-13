"""Shared fixtures for ResearchScope tests."""
from __future__ import annotations

import pytest

from src.normalization.schema import Paper


@pytest.fixture()
def sample_paper() -> Paper:
    return Paper(
        id="arxiv:2401.00001",
        title="Attention Is All You Need Revisited",
        abstract=(
            "We revisit the Transformer architecture and propose improvements "
            "to the attention mechanism. Our experiments show state-of-the-art "
            "results on multiple benchmarks. However, a limitation of our approach "
            "is the quadratic complexity. Future work should explore linear attention."
        ),
        authors=["Alice Smith", "Bob Jones"],
        year=2024,
        venue="arXiv",
        url="https://arxiv.org/abs/2401.00001",
        source="arxiv",
        tags=["Transformers", "NLP"],
        difficulty="intermediate",
        citations=42,
    )


@pytest.fixture()
def sample_papers(sample_paper: Paper) -> list[Paper]:
    p2 = Paper(
        id="arxiv:2401.00002",
        title="Large Language Models in the Wild",
        abstract=(
            "We study the deployment of large language models (LLMs) in production "
            "environments. We identify open challenges including hallucination and "
            "robustness. Future work includes better alignment techniques."
        ),
        authors=["Carol White"],
        year=2023,
        venue="arXiv",
        source="arxiv",
        tags=["LLMs"],
        difficulty="intermediate",
        citations=10,
    )
    return [sample_paper, p2]
