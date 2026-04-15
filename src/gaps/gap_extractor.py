"""
Research Gap Engine — three-layer extraction.

Layer 1  Explicit gaps   — direct quotes from limitations/future-work language
Layer 2  Pattern gaps    — inferred by recurring weakness patterns across papers
Layer 3  Starter gaps    — beginner-friendly research directions and ideas

Outputs are presented as grounded *signals*, not absolute truth.
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict

from src.normalization.schema import Paper, ResearchGap

# ── Layer 1: Explicit gap sentence patterns ───────────────────────────────────

_EXPLICIT_PATTERN = re.compile(
    r"(?:"
    r"limitation|future work|open problem|open challenge|open question|"
    r"remains to be|yet to be|not address|unsolved|we leave|"
    r"promising direction|future direction|further research needed|"
    r"our approach does not|we do not handle|we cannot|"
    r"cannot handle|fails? to|struggles? with|does not scale|"
    r"challenging to|difficult to|out of scope"
    r")[^.!?]{5,200}[.!?]",
    re.IGNORECASE,
)

# ── Layer 2: Pattern gap signals ─────────────────────────────────────────────
# (label, regex) — label is used to group recurring weaknesses across papers

_PATTERN_SIGNALS: list[tuple[str, re.Pattern[str]]] = [
    ("Benchmark overfitting",
     re.compile(r"\b(overfit|dataset.specific|not generaliz|narrow benchmark)\b", re.IGNORECASE)),
    ("Weak robustness testing",
     re.compile(r"\b(robustness|adversarial|distribution shift|out.of.domain|OOD)\b", re.IGNORECASE)),
    ("Missing low-resource coverage",
     re.compile(r"\b(low.resource|under.represented|minority language|low.data)\b", re.IGNORECASE)),
    ("Narrow evaluation domains",
     re.compile(r"\b(English only|single domain|limited domain|domain.specific)\b", re.IGNORECASE)),
    ("High compute cost",
     re.compile(r"\b(computationally expensive|high cost|resource.intensive|GPU.intensive)\b", re.IGNORECASE)),
    ("Lack of interpretability",
     re.compile(r"\b(black.box|lack.*interpret|not interpretable|opaque)\b", re.IGNORECASE)),
    ("Missing long-form evaluation",
     re.compile(r"\b(long.form|extended context|long document|long context)\b", re.IGNORECASE)),
    ("Dataset bias / fairness",
     re.compile(r"\b(bias|fairness|stereotyp|gender bias|racial)\b", re.IGNORECASE)),
    ("Limited multilinguality",
     re.compile(r"\b(multilingual|cross.lingual|non.English|language transfer)\b", re.IGNORECASE)),
    ("Hallucination / factuality",
     re.compile(r"\bhallucin|\bfactual error\b|\bfactuality\b|\bconfabulation\b", re.IGNORECASE)),
]

# ── Layer 3: Starter idea templates ──────────────────────────────────────────

_STARTER_TEMPLATES: dict[str, list[str]] = {
    "Large Language Models": [
        "Fine-tune an open-source LLM on a domain-specific dataset and evaluate factuality.",
        "Build a RAG pipeline and compare retrieval strategies on a small test set.",
        "Measure LLM calibration: does the model know what it doesn't know?",
    ],
    "Transformer Architectures": [
        "Implement a Transformer from scratch in PyTorch.",
        "Visualise attention heads on your own text samples.",
        "Compare different positional encoding schemes on a text classification task.",
    ],
    "Diffusion Models": [
        "Train a small diffusion model on a custom image dataset (e.g. 64x64 icons).",
        "Evaluate how conditioning signal quality affects generation diversity.",
    ],
    "Reinforcement Learning": [
        "Train a DQN agent on a simple OpenAI Gym environment.",
        "Add reward shaping to reduce sample inefficiency on a gridworld task.",
        "Compare PPO and REINFORCE on a continuous-action environment.",
    ],
    "Computer Vision": [
        "Train a classifier on a small custom dataset using transfer learning.",
        "Implement data augmentation techniques and measure their impact.",
        "Reproduce a CIFAR-10 baseline with a modern architecture.",
    ],
    "Multimodal Learning": [
        "Fine-tune a CLIP model on a domain-specific image-caption dataset.",
        "Evaluate vision-language models on your own image set.",
    ],
    "Code Generation & Synthesis": [
        "Evaluate open-source code LLMs on a custom set of algorithmic problems.",
        "Build a test-case generator to evaluate code correctness automatically.",
    ],
    "Retrieval-Augmented Generation": [
        "Build a RAG pipeline and compare different chunking and retrieval strategies.",
        "Evaluate how knowledge freshness affects LLM answer quality in a RAG setup.",
    ],
    "AI Safety & Alignment": [
        "Red-team a small open-source LLM with structured adversarial prompts.",
        "Measure refusal rates across different safety-sensitive categories.",
    ],
    "AI Agents & Tool Use": [
        "Build a simple tool-using agent and evaluate it on a benchmark task.",
        "Compare ReAct and plan-then-execute prompting strategies.",
    ],
    "_default": [
        "Reproduce the paper's baseline experiment.",
        "Apply the method to a new domain dataset.",
        "Write a blog post explaining the gap and possible directions.",
        "Run an ablation study removing one component of the method.",
    ],
}

# Aliases — short tag forms point to the same templates as their full names
_STARTER_ALIASES: dict[str, str] = {
    "LLMs":           "Large Language Models",
    "Transformers":   "Transformer Architectures",
    "RL":             "Reinforcement Learning",
    "RAG":            "Retrieval-Augmented Generation",
    "Multimodal":     "Multimodal Learning",
    "AI Agents":      "AI Agents & Tool Use",
    "Code Generation":"Code Generation & Synthesis",
}

def _starter_projects(tags: list[str]) -> list[str]:
    for tag in tags:
        resolved = _STARTER_ALIASES.get(tag, tag)
        if resolved in _STARTER_TEMPLATES:
            return _STARTER_TEMPLATES[resolved]
    return _STARTER_TEMPLATES["_default"]



# ── GapExtractor ─────────────────────────────────────────────────────────────

class GapExtractor:
    """Extract research gaps using all three layers."""

    def extract(self, papers: list[Paper]) -> list[ResearchGap]:
        gaps: list[ResearchGap] = []
        gaps.extend(self._layer1_explicit(papers))
        gaps.extend(self._layer2_patterns(papers))
        gaps.extend(self._layer3_starters(papers))

        # Deduplicate by (topic, gap_type) — keep highest frequency
        seen: dict[tuple[str, str], ResearchGap] = {}
        for g in gaps:
            key = (g.topic, g.gap_type, g.title[:40])
            if key not in seen or g.frequency > seen[key].frequency:
                seen[key] = g

        result = sorted(seen.values(), key=lambda g: (-g.frequency, g.gap_type))
        return result

    # ── Layer 1 ───────────────────────────────────────────────────────────────

    def _layer1_explicit(self, papers: list[Paper]) -> list[ResearchGap]:
        topic_buckets: dict[str, dict] = defaultdict(
            lambda: {"descs": [], "paper_ids": [], "tags": []}
        )

        for paper in papers:
            text = paper.abstract
            if not text:
                continue
            matches = _EXPLICIT_PATTERN.findall(text)
            if not matches:
                continue

            topic = paper.tags[0] if paper.tags else "General AI"
            bucket = topic_buckets[topic]
            bucket["paper_ids"].append(paper.id)
            bucket["tags"] = paper.tags
            for m in matches:
                clean = m.strip()
                if clean and clean not in bucket["descs"]:
                    bucket["descs"].append(clean)

        gaps = []
        for topic, bucket in topic_buckets.items():
            desc = bucket["descs"][0] if bucket["descs"] else f"Open challenges in {topic}"
            title = self._make_title(desc, topic)
            gaps.append(ResearchGap(
                gap_id=str(uuid.uuid4()),
                topic=topic,
                title=title,
                description=str(desc),
                evidence_paper_ids=bucket["paper_ids"],
                gap_type="explicit",
                confidence=0.8,
                starter_idea=_starter_projects(bucket["tags"])[0],
                frequency=len(bucket["paper_ids"]),
                suggested_projects=_starter_projects(bucket["tags"]),
            ))
        return gaps

    # ── Layer 2 ───────────────────────────────────────────────────────────────

    def _layer2_patterns(self, papers: list[Paper]) -> list[ResearchGap]:
        signal_buckets: dict[str, dict] = defaultdict(
            lambda: {"paper_ids": [], "tags": set()}
        )

        for paper in papers:
            text = f"{paper.title} {paper.abstract}"
            for label, pattern in _PATTERN_SIGNALS:
                if pattern.search(text):
                    signal_buckets[label]["paper_ids"].append(paper.id)
                    signal_buckets[label]["tags"].update(paper.tags)

        gaps = []
        for label, bucket in signal_buckets.items():
            freq = len(bucket["paper_ids"])
            if freq < 2:
                continue  # require at least 2 papers for a pattern gap
            tags = list(bucket["tags"])
            topic = tags[0] if tags else "General AI"
            gaps.append(ResearchGap(
                gap_id=str(uuid.uuid4()),
                topic=topic,
                title=label,
                description=(
                    f"Pattern detected across {freq} papers: '{label}' is a recurring "
                    f"challenge in {topic} research. Papers frequently mention this as a "
                    f"limitation or unsolved problem."
                ),
                evidence_paper_ids=bucket["paper_ids"][:10],
                gap_type="pattern",
                confidence=min(0.4 + freq * 0.05, 0.9),
                starter_idea=_starter_projects(tags)[0] if tags else _STARTER_TEMPLATES["_default"][0],
                frequency=freq,
                suggested_projects=_starter_projects(tags),
            ))
        return sorted(gaps, key=lambda g: -g.frequency)

    # ── Layer 3 ───────────────────────────────────────────────────────────────

    def _layer3_starters(self, papers: list[Paper]) -> list[ResearchGap]:
        """Generate beginner-friendly research directions from prevalent topics."""
        tag_count: dict[str, list[str]] = defaultdict(list)
        for paper in papers:
            for tag in paper.tags:
                tag_count[tag].append(paper.id)

        gaps = []
        for tag, paper_ids in sorted(tag_count.items(), key=lambda x: -len(x[1])):
            resolved = _STARTER_ALIASES.get(tag, tag)
            if resolved not in _STARTER_TEMPLATES:
                continue
            ideas = _STARTER_TEMPLATES[resolved]
            for i, idea in enumerate(ideas[:2]):
                gaps.append(ResearchGap(
                    gap_id=str(uuid.uuid4()),
                    topic=tag,
                    title=f"Starter idea: {idea[:60]}…" if len(idea) > 60 else f"Starter idea: {idea}",
                    description=(
                        f"Beginner-friendly research direction in {tag}. "
                        f"Based on {len(paper_ids)} tracked papers in this area. "
                        f"Idea: {idea}"
                    ),
                    evidence_paper_ids=paper_ids[:5],
                    gap_type="starter",
                    confidence=0.7,
                    starter_idea=idea,
                    frequency=len(paper_ids),
                    suggested_projects=ideas,
                ))
        return gaps

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_title(description: str, topic: str) -> str:
        """Turn a raw limitation sentence into a short gap title."""
        desc = description.strip().rstrip(".!?")
        # try to extract the first meaningful phrase
        if len(desc) <= 60:
            return desc.capitalize()
        # shorten to first clause
        for sep in [";", ",", "—", "–", " but ", " and "]:
            if sep in desc[:80]:
                return desc[:desc.index(sep, 0, 80)].strip().capitalize()
        return f"Open challenge in {topic}"
