"""
Topic clusterer: groups papers by tag into Topic objects with trend scores,
starter/frontier packs, and gap summaries.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from src.normalization.schema import Paper, Topic

_CURRENT_YEAR = datetime.now(timezone.utc).year

# ── Static topic metadata ─────────────────────────────────────────────────────

_TOPIC_DIFFICULTY: dict[str, str] = {
    "LLMs": "L2", "Transformers": "L2", "Diffusion Models": "L3", "RL": "L3",
    "GNN": "L3", "RAG": "L2", "QA": "L1", "Translation": "L1", "IE": "L2",
    "Sentiment Analysis": "L1", "Image Generation": "L2", "Computer Vision": "L2",
    "Speech": "L2", "Code Generation": "L2", "Federated Learning": "L3",
    "Continual Learning": "L3", "Prompting": "L1", "Model Compression": "L2",
    "Multimodal": "L2", "Summarization": "L1", "Deep Learning": "L2",
    "NLP": "L1", "Machine Learning": "L1", "AI Safety & Alignment": "L2",
    "AI Agents": "L2", "Information Retrieval": "L2",
}

_LEVEL_TO_LABEL: dict[str, str] = {
    "L1": "beginner", "L2": "intermediate", "L3": "advanced", "L4": "frontier"
}

_PREREQUISITES: dict[str, list[str]] = {
    "Transformers":            ["Deep Learning", "NLP"],
    "LLMs":                    ["Transformers", "NLP"],
    "Diffusion Models":        ["Deep Learning", "Image Generation"],
    "RL":                      ["Machine Learning"],
    "GNN":                     ["Deep Learning", "Machine Learning"],
    "RAG":                     ["LLMs", "Information Retrieval"],
    "Federated Learning":      ["Machine Learning"],
    "Continual Learning":      ["Machine Learning", "Deep Learning"],
    "AI Safety & Alignment":   ["LLMs", "RL"],
    "AI Agents":               ["LLMs", "RL"],
    "Multimodal":              ["Transformers", "Computer Vision"],
    "Code Generation":         ["LLMs"],
}

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "LLMs": ["large language model", "llm", "gpt", "instruction tuning"],
    "Transformers": ["transformer", "self-attention", "bert", "attention mechanism"],
    "Diffusion Models": ["diffusion", "score-based", "denoising", "ddpm"],
    "RL": ["reinforcement learning", "policy gradient", "reward", "rlhf"],
    "RAG": ["retrieval-augmented", "dense retrieval", "rag"],
    "Multimodal": ["multimodal", "vision-language", "clip", "vqa"],
    "Computer Vision": ["image classification", "object detection", "vision"],
    "NLP": ["natural language processing", "text", "language"],
}

# ── Trend keywords: topics that signal cutting-edge / trending work ───────────
_TRENDING_TOPICS = {
    "LLMs", "Diffusion Models", "RAG", "Multimodal", "AI Safety & Alignment",
    "AI Agents", "Code Generation",
}


def _slug(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")


class TopicClusterer:
    """Group papers by tag into enriched Topic objects."""

    def cluster(self, papers: list[Paper]) -> list[Topic]:
        tag_to_papers: dict[str, list[Paper]] = {}
        for paper in papers:
            for tag in paper.tags:
                tag_to_papers.setdefault(tag, []).append(paper)

        topics: list[Topic] = []
        all_tags = list(tag_to_papers.keys())

        for tag, tag_papers in tag_to_papers.items():
            level = _TOPIC_DIFFICULTY.get(tag, "L2")
            diff_label = _LEVEL_TO_LABEL.get(level, "intermediate")

            # related topics by paper-count proximity
            related = sorted(
                [t for t in all_tags if t != tag],
                key=lambda t: -len(tag_to_papers[t])
            )[:5]

            # starter pack: L1/L2 papers sorted by read_first_score
            starter = sorted(
                [p for p in tag_papers if p.difficulty_level in ("L1", "L2")],
                key=lambda p: -p.read_first_score,
            )[:5]

            # frontier pack: L3/L4 papers sorted by paper_score
            frontier = sorted(
                [p for p in tag_papers if p.difficulty_level in ("L3", "L4")],
                key=lambda p: -p.paper_score,
            )[:5]

            trend_score = self._trend_score(tag, tag_papers)
            gap_summary = self._gap_summary(tag, tag_papers)

            topics.append(Topic(
                id=_slug(tag),
                name=tag,
                keywords=_TOPIC_KEYWORDS.get(tag, [tag.lower()]),
                paper_ids=[p.id for p in tag_papers],
                trend_score=trend_score,
                gap_summary=gap_summary,
                starter_pack_ids=[p.id for p in starter],
                frontier_pack_ids=[p.id for p in frontier],
                difficulty=diff_label,
                prerequisites=_PREREQUISITES.get(tag, []),
                related_topics=related,
            ))

        topics.sort(key=lambda t: (-t.trend_score, -len(t.paper_ids)))
        return topics

    @staticmethod
    def _trend_score(tag: str, papers: list[Paper]) -> float:
        recent = sum(1 for p in papers if _CURRENT_YEAR - p.year <= 2)
        total = len(papers) or 1
        recency_ratio = recent / total
        base = 10.0 if tag in _TRENDING_TOPICS else 5.0
        return round(min(base * recency_ratio + len(papers) * 0.01, 10.0), 2)

    @staticmethod
    def _gap_summary(tag: str, papers: list[Paper]) -> str:
        limitation_count = sum(1 for p in papers if p.limitations)
        future_count = sum(1 for p in papers if p.future_work)
        if limitation_count == 0 and future_count == 0:
            return f"No explicit gaps extracted yet for {tag}."
        return (
            f"{limitation_count} papers in {tag} report explicit limitations; "
            f"{future_count} describe future work directions."
        )
