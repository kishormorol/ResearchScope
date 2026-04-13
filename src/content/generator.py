"""Content generation helpers."""
from __future__ import annotations

import re

from src.normalization.schema import Paper

_WHY_TEMPLATES: dict[str, str] = {
    "LLMs": "advances our understanding of large language models, which are transforming how we interact with and extract knowledge from text",
    "Transformers": "extends the capabilities of Transformer architectures that underpin most modern NLP systems",
    "Diffusion Models": "pushes the frontier of generative modelling, enabling higher-quality and more controllable content creation",
    "RL": "contributes to reinforcement learning, a key paradigm for training autonomous agents and decision-making systems",
    "GNN": "broadens the applicability of graph neural networks for structured data and relational reasoning",
    "RAG": "improves retrieval-augmented generation, helping language models ground their responses in verified knowledge",
    "Computer Vision": "advances computer vision, enabling machines to better interpret and understand visual information",
    "Speech": "improves speech recognition and synthesis, making voice interfaces more accessible and accurate",
    "Code Generation": "reduces the barrier to software development by automating code writing and understanding",
    "Multimodal": "bridges the gap between vision and language, enabling richer multi-modal AI applications",
    "Federated Learning": "enables privacy-preserving machine learning across distributed data sources",
    "Model Compression": "makes powerful models practical for deployment on resource-constrained devices",
    "_default": "represents a meaningful contribution to its field and opens new research directions",
}


def _first_n_sentences(text: str, n: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[:n])


class ContentGenerator:
    """Generate human-readable summaries and 'why it matters' blurbs."""

    def generate_summary(self, paper: Paper) -> str:
        if not paper.abstract:
            return ""
        return _first_n_sentences(paper.abstract, 2)

    def generate_why_it_matters(self, paper: Paper) -> str:
        title = paper.title or "This work"
        for tag in paper.tags:
            if tag in _WHY_TEMPLATES:
                return f"{title} {_WHY_TEMPLATES[tag]}."
        return f"{title} {_WHY_TEMPLATES['_default']}."
