"""Research gap extraction from paper abstracts."""
from __future__ import annotations

import re
import uuid
from collections import defaultdict

from src.normalization.schema import Paper, ResearchGap

_GAP_PATTERNS = re.compile(
    r"(limitation|future work|open problem|open challenge|open question|"
    r"remains to be|yet to be|not addressed|unsolved|"
    r"promising direction|future direction|further research|"
    r"our approach does not|we do not|we cannot|"
    r"cannot handle|fails to|struggles? with)[^.!?]{0,200}[.!?]",
    re.IGNORECASE,
)

_PROJECT_TEMPLATES: dict[str, list[str]] = {
    "LLMs": [
        "Fine-tune a small open-source LLM on a domain-specific dataset",
        "Build a retrieval-augmented generation (RAG) chatbot",
        "Evaluate LLM factuality on a custom benchmark",
    ],
    "Transformers": [
        "Implement a Transformer from scratch in PyTorch",
        "Apply a pre-trained Transformer to a text classification task",
        "Visualize attention heads on your own text samples",
    ],
    "Computer Vision": [
        "Train an image classifier on a small custom dataset",
        "Implement data-augmentation techniques and measure impact on accuracy",
        "Reproduce a CIFAR-10 baseline with a modern CNN",
    ],
    "RL": [
        "Train a DQN agent on a simple OpenAI Gym environment",
        "Implement REINFORCE for a grid-world navigation task",
        "Add reward shaping to improve sample efficiency",
    ],
    "NLP": [
        "Build a text classification pipeline with scikit-learn",
        "Evaluate tokenisation strategies on low-resource languages",
        "Create a dataset annotation pipeline with a simple UI",
    ],
    "_default": [
        "Reproduce the paper's baseline experiment",
        "Apply the method to a new domain dataset",
        "Write a literature review blog post summarising the research gap",
    ],
}


def _projects_for_tags(tags: list[str]) -> list[str]:
    for tag in tags:
        if tag in _PROJECT_TEMPLATES:
            return _PROJECT_TEMPLATES[tag]
    return _PROJECT_TEMPLATES["_default"]


class GapExtractor:
    """Extract research gaps from paper abstracts."""

    def extract(self, papers: list[Paper]) -> list[ResearchGap]:
        topic_gaps: dict[str, dict] = defaultdict(
            lambda: {"descriptions": [], "paper_ids": [], "tags": []}
        )

        for paper in papers:
            matches = _GAP_PATTERNS.findall(paper.abstract)
            if not matches:
                continue

            topic = paper.tags[0] if paper.tags else "General"
            entry = topic_gaps[topic]
            entry["paper_ids"].append(paper.id)
            entry["tags"] = paper.tags
            for keyword in matches:
                desc = keyword.strip()
                if desc and desc not in entry["descriptions"]:
                    entry["descriptions"].append(desc)

        gaps: list[ResearchGap] = []
        for topic, entry in topic_gaps.items():
            description = (
                entry["descriptions"][0]
                if entry["descriptions"]
                else f"Open challenges in {topic}"
            )
            gaps.append(
                ResearchGap(
                    id=str(uuid.uuid4()),
                    topic=topic,
                    description=str(description),
                    source_paper_ids=entry["paper_ids"],
                    frequency=len(entry["paper_ids"]),
                    suggested_projects=_projects_for_tags(entry["tags"]),
                )
            )

        gaps.sort(key=lambda g: -g.frequency)
        return gaps
