"""Shared test fixtures."""
from __future__ import annotations

import pytest

from src.normalization.schema import Author, Lab, Paper, ResearchGap, Topic, University


@pytest.fixture()
def sample_paper() -> Paper:
    return Paper(
        id="arxiv:2401.00001",
        source="arxiv",
        source_type="preprint",
        title="Attention Is All You Need Revisited",
        abstract=(
            "We propose a novel transformer architecture that improves multi-head "
            "attention efficiency. Our experiments show state-of-the-art results on "
            "multiple benchmarks. However, a limitation of our approach is the "
            "quadratic complexity with sequence length. Future work should explore "
            "linear attention mechanisms for long-context tasks."
        ),
        authors=["Alice Smith", "Bob Jones"],
        year=2024,
        venue="arXiv",
        paper_url="https://arxiv.org/abs/2401.00001",
        tags=["Transformers", "NLP"],
        difficulty_level="L2",
        citations=42,
        conference_rank="",
    )


@pytest.fixture()
def conference_paper() -> Paper:
    return Paper(
        id="acl:2024.acl-long.1",
        source="acl_anthology",
        source_type="conference",
        title="Large Language Models for Low-Resource NLP",
        abstract=(
            "We study the use of large language models (LLMs) for low-resource "
            "natural language processing tasks. We demonstrate zero-shot and few-shot "
            "performance on ten under-represented languages. We cannot handle "
            "languages with no digital presence. Federated approaches are a "
            "promising direction for future work."
        ),
        authors=["Carol White", "Dave Green", "Eve Brown", "Frank Lee"],
        year=2024,
        venue="ACL",
        conference_rank="A*",
        paper_url="https://aclanthology.org/2024.acl-long.1",
        tags=["LLMs", "NLP"],
        difficulty_level="L2",
        citations=15,
    )


@pytest.fixture()
def sample_papers(sample_paper: Paper, conference_paper: Paper) -> list[Paper]:
    p3 = Paper(
        id="arxiv:2401.00003",
        source="arxiv",
        title="A Survey of Reinforcement Learning",
        abstract=(
            "This survey provides an overview of reinforcement learning methods "
            "from Q-learning to policy gradient approaches. We cover recent advances "
            "and future directions in the field."
        ),
        authors=["Grace Hill"],
        year=2023,
        venue="arXiv",
        tags=["RL", "Machine Learning"],
        difficulty_level="L1",
        citations=100,
    )
    p4 = Paper(
        id="arxiv:2401.00004",
        source="arxiv",
        title="Diffusion Models Beat GANs on Image Generation",
        abstract=(
            "We show that denoising diffusion probabilistic models surpass "
            "generative adversarial networks on standard image generation benchmarks. "
            "Our approach does not scale well to very high resolution images. "
            "Future work includes latent diffusion for efficiency."
        ),
        authors=["Henry Davis", "Iris Kim"],
        year=2024,
        venue="arXiv",
        tags=["Diffusion Models", "Computer Vision"],
        difficulty_level="L3",
        citations=250,
    )
    return [sample_paper, conference_paper, p3, p4]
