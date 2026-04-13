"""Keyword-based paper tagger."""
from __future__ import annotations

import re

from src.normalization.schema import Paper

# (pattern, tag) pairs – ordered from most specific to least specific
_RULES: list[tuple[str, str]] = [
    (r"large language model|llm\b", "LLMs"),
    (r"transformer|self[- ]attention|multi[- ]head attention", "Transformers"),
    (r"diffusion model|denoising diffusion|score.based", "Diffusion Models"),
    (r"reinforcement learning|reward model|policy gradient|rlhf", "RL"),
    (r"graph neural|graph convolution|knowledge graph", "GNN"),
    (r"retrieval.augmented|retrieval augmented|rag\b", "RAG"),
    (r"question answering|reading comprehension", "QA"),
    (r"machine translation|neural machine translation|nmt\b", "Translation"),
    (r"named entity|relation extraction|information extraction", "IE"),
    (r"sentiment analysis|opinion mining", "Sentiment Analysis"),
    (r"image generation|text.to.image|image synthesis", "Image Generation"),
    (r"object detection|image classification|semantic segmentation", "Computer Vision"),
    (r"speech recognition|automatic speech|asr\b", "Speech"),
    (r"code generation|program synthesis|code completion", "Code Generation"),
    (r"federated learning", "Federated Learning"),
    (r"continual learning|catastrophic forgetting", "Continual Learning"),
    (r"few.shot|zero.shot|in.context learning|prompt", "Prompting"),
    (r"knowledge distillation|model compression|pruning", "Model Compression"),
    (r"multimodal|vision.language|visual grounding", "Multimodal"),
    (r"summarization|abstractive summarization", "Summarization"),
    (r"neural network|deep learning|deep neural", "Deep Learning"),
]

_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern, re.IGNORECASE), tag) for pattern, tag in _RULES
]


class PaperTagger:
    """Enrich paper tags from abstract/title keyword matching."""

    def tag(self, paper: Paper) -> Paper:
        haystack = f"{paper.title} {paper.abstract}".lower()
        existing = set(paper.tags)
        for pattern, tag_name in _COMPILED:
            if tag_name not in existing and pattern.search(haystack):
                existing.add(tag_name)
        paper.tags = sorted(existing)
        return paper
