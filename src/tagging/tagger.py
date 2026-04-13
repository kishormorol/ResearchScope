"""
Paper tagger: assigns topic tags and detects paper_type from text.
Topics are loaded from config/topics.yaml when available; the built-in
keyword table is used as fallback so the module works without PyYAML.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.normalization.schema import Paper


# ── Config ────────────────────────────────────────────────────────────────────

def _load_topics() -> dict[str, Any]:
    cfg_path = Path(__file__).parent.parent.parent / "config" / "topics.yaml"
    try:
        import yaml  # type: ignore
        with open(cfg_path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        pass
    return {}


# ── Built-in tag rules (pattern, human-readable tag) ─────────────────────────

_BUILTIN_RULES: list[tuple[str, str]] = [
    (r"large language model|llm\b|gpt|chatgpt|instruction.tun|chat model",      "LLMs"),
    (r"transformer|self[- ]attention|multi[- ]head attention|bert\b",             "Transformers"),
    (r"diffusion model|denoising diffusion|score.based|ddpm|latent diffusion",    "Diffusion Models"),
    (r"reinforcement learning|reward model|policy gradient|rlhf\b|dqn\b|ppo\b", "RL"),
    (r"graph neural|graph convolution|knowledge graph|gcn\b|gat\b",              "GNN"),
    (r"retrieval.augmented|retrieval augmented|rag\b|dense retrieval",            "RAG"),
    (r"question answering|reading comprehension|qa\b",                            "QA"),
    (r"machine translation|neural machine translation|nmt\b",                     "Translation"),
    (r"named entity|relation extraction|information extraction",                  "IE"),
    (r"sentiment analysis|opinion mining",                                        "Sentiment Analysis"),
    (r"image generation|text.to.image|image synthesis|stable diffusion",         "Image Generation"),
    (r"object detection|image classification|semantic segmentation|resnet\b",    "Computer Vision"),
    (r"speech recognition|automatic speech|asr\b|whisper\b|text.to.speech",      "Speech"),
    (r"code generation|program synthesis|code completion|codex\b|copilot",        "Code Generation"),
    (r"federated learning",                                                        "Federated Learning"),
    (r"continual learning|catastrophic forgetting|lifelong learning",              "Continual Learning"),
    (r"few.shot|zero.shot|in.context learning|chain.of.thought|cot\b",            "Prompting"),
    (r"knowledge distillation|model compression|pruning|quantiz",                 "Model Compression"),
    (r"multimodal|vision.language|visual grounding|vqa\b|clip\b|llava\b",         "Multimodal"),
    (r"summarization|abstractive summarization",                                   "Summarization"),
    (r"deep learning|neural network|deep neural",                                  "Deep Learning"),
    (r"natural language processing|text classification|text mining",               "NLP"),
    (r"machine learning|gradient descent|supervised learning",                     "Machine Learning"),
    (r"ai safety|alignment|hallucination|red teaming|constitutional ai",           "AI Safety & Alignment"),
    (r"autonomous agent|agent framework|tool use|react\b.*agent|function calling", "AI Agents"),
    (r"information retrieval|search engine|document ranking|bm25\b",              "Information Retrieval"),
    (r"artificial intelligence\b",                                                 "Artificial Intelligence"),
]

_COMPILED_TAGS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE), tag) for p, tag in _BUILTIN_RULES
]


# ── Paper-type rules ──────────────────────────────────────────────────────────

_TYPE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsurvey\b|\boverview\b|\bcomprehensive review\b",      re.IGNORECASE), "survey"),
    (re.compile(r"\bbenchmark\b|\bleaderboard\b|\bcomparative study\b",   re.IGNORECASE), "benchmark"),
    (re.compile(r"\bdataset\b|\bcorpus\b|\bannotation\b|\bcollection\b",  re.IGNORECASE), "dataset"),
    (re.compile(r"\bsystems?\b.*\bdesign\b|\bscalable\b|\binfrastructure\b|\bdeployment\b",
                re.IGNORECASE), "systems"),
    (re.compile(r"\btheorem\b|\bproof\b|\blemma\b|\bconvergence\b",       re.IGNORECASE), "theory"),
    (re.compile(r"\btutorial\b|\bprimer\b|\bintroduction to\b|\bgetting started\b",
                re.IGNORECASE), "tutorial"),
    (re.compile(r"\bposition paper\b|\bwe argue\b|\bwe call for\b",       re.IGNORECASE), "position"),
    (re.compile(r"\bnegative result\b|\bfailed\b|\bdoes not\b.*improve",  re.IGNORECASE), "negative_result"),
    (re.compile(r"\breplication\b|\breproduc\b",                          re.IGNORECASE), "replication"),
    (re.compile(r"\bwe propose\b|\bwe introduce\b|\bnovel method\b|\bnew (model|approach|architecture)\b",
                re.IGNORECASE), "methods"),
    (re.compile(r"\bwe (conduct|run|perform) experiment|\bempirical (study|analysis|evaluation)\b",
                re.IGNORECASE), "empirical"),
]


class PaperTagger:
    """
    Enrich paper.tags from title+abstract keywords.
    Detect paper.paper_type from structural language cues.
    """

    def tag(self, paper: Paper) -> Paper:
        haystack = f"{paper.title} {paper.abstract}"
        existing = set(paper.tags)

        for pattern, tag_name in _COMPILED_TAGS:
            if tag_name not in existing and pattern.search(haystack):
                existing.add(tag_name)

        paper.tags = sorted(existing)

        if not paper.paper_type:
            paper.paper_type = self._detect_type(haystack)

        return paper

    @staticmethod
    def _detect_type(text: str) -> str:
        for pattern, ptype in _TYPE_RULES:
            if pattern.search(text):
                return ptype
        return "methods"  # sensible default
