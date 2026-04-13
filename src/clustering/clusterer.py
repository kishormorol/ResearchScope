"""Topic clustering: group papers by their tags."""
from __future__ import annotations

import re

from src.normalization.schema import Paper, Topic

# Topic-level difficulty defaults
_TOPIC_DIFFICULTY: dict[str, str] = {
    "LLMs": "intermediate",
    "Transformers": "intermediate",
    "Diffusion Models": "advanced",
    "RL": "advanced",
    "GNN": "advanced",
    "RAG": "intermediate",
    "QA": "beginner",
    "Translation": "beginner",
    "IE": "intermediate",
    "Sentiment Analysis": "beginner",
    "Image Generation": "intermediate",
    "Computer Vision": "intermediate",
    "Speech": "intermediate",
    "Code Generation": "intermediate",
    "Federated Learning": "advanced",
    "Continual Learning": "advanced",
    "Prompting": "beginner",
    "Model Compression": "intermediate",
    "Multimodal": "intermediate",
    "Summarization": "beginner",
    "Deep Learning": "intermediate",
    "NLP": "intermediate",
    "Artificial Intelligence": "beginner",
    "Machine Learning": "intermediate",
}

_PREREQUISITES: dict[str, list[str]] = {
    "Transformers": ["Deep Learning", "NLP"],
    "LLMs": ["Transformers", "NLP"],
    "Diffusion Models": ["Deep Learning", "Image Generation"],
    "RL": ["Machine Learning"],
    "GNN": ["Deep Learning", "Machine Learning"],
    "RAG": ["LLMs", "Information Retrieval"],
    "Federated Learning": ["Machine Learning"],
    "Continual Learning": ["Machine Learning", "Deep Learning"],
}


def _slug(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")


class TopicClusterer:
    """Group papers by tag into Topic objects."""

    def cluster(self, papers: list[Paper]) -> list[Topic]:
        tag_to_paper_ids: dict[str, list[str]] = {}
        for paper in papers:
            for tag in paper.tags:
                tag_to_paper_ids.setdefault(tag, []).append(paper.id)

        topics: list[Topic] = []
        all_tags = list(tag_to_paper_ids.keys())
        for tag, paper_ids in tag_to_paper_ids.items():
            related = [t for t in all_tags if t != tag and tag_to_paper_ids.get(t)]
            # pick up to 5 related topics by paper-count proximity
            related.sort(key=lambda t: -len(tag_to_paper_ids[t]))
            topics.append(
                Topic(
                    id=_slug(tag),
                    name=tag,
                    paper_ids=paper_ids,
                    difficulty=_TOPIC_DIFFICULTY.get(tag, "intermediate"),
                    prerequisites=_PREREQUISITES.get(tag, []),
                    related_topics=related[:5],
                )
            )

        topics.sort(key=lambda t: -len(t.paper_ids))
        return topics
