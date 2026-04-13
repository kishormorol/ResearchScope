"""
Difficulty assessor: assigns L1–L4 levels with a plain-English reason.

Levels:
  L1  Beginner     — no ML background needed; surveys, overviews, tutorials
  L2  Intermediate — undergraduate ML/NLP; most applied papers
  L3  Advanced     — graduate-level math/ML; architecture papers, theory
  L4  Frontier     — cutting-edge research requiring domain mastery
"""
from __future__ import annotations

import re

from src.normalization.schema import Paper

# ── Level patterns ────────────────────────────────────────────────────────────

_L1_POSITIVE = re.compile(
    r"\b(survey|overview|tutorial|introduction to|beginners?|primer|"
    r"getting started|hands.on|explainer|we explain|"
    r"accessible|no prior|from scratch)\b",
    re.IGNORECASE,
)

_L4_POSITIVE = re.compile(
    r"\b(theorem|proof|lemma|corollary|convergence guarantee|"
    r"variational inference|bayesian|stochastic|manifold|topology|"
    r"eigenvalue|information.theoretic|pac.learning|regret bound|"
    r"neural architecture search|nas\b|causal inference|"
    r"adversarial robustness|certified defense)\b",
    re.IGNORECASE,
)

_L3_POSITIVE = re.compile(
    r"\b(novel architecture|architecture design|custom (loss|objective)|"
    r"attention variant|gradient descent|backpropagation|"
    r"adversarial training|generative adversarial|"
    r"variational autoencoder|vae\b|latent space|"
    r"pretraining|self.supervised|contrastive|"
    r"hyperparameter|ablation study|cross.entropy|"
    r"multi.task|continual|catastrophic)\b",
    re.IGNORECASE,
)

_L1_TAGS = {
    "Sentiment & Opinion Analysis", "Text Summarization", "Question Answering",
    "Machine Translation", "Prompting & In-Context Learning",
    "Text Classification", "Benchmarking & Evaluation",
}
_L3_TAGS = {
    "Diffusion Models", "Reinforcement Learning", "Graph Neural Networks",
    "Federated & Privacy-Preserving Learning", "Continual Learning",
    "AI Safety & Alignment", "Mixture of Experts", "State Space Models",
    "RLHF & Preference Alignment",
}
_L4_TAGS = set()  # reserved; currently detected by text patterns only


class DifficultyAssessor:
    """Assign L1–L4 difficulty level with a plain-English reason."""

    def assess(self, paper: Paper) -> Paper:
        text = f"{paper.title} {paper.abstract}"
        level, reason = self._classify(text, paper.tags, paper.paper_type)
        paper.difficulty_level = level
        paper.difficulty_reason = reason
        return paper

    @staticmethod
    def _classify(text: str, tags: list[str], paper_type: str) -> tuple[str, str]:
        tag_set = set(tags)

        # ── L1 ────────────────────────────────────────────────────────────────
        if _L1_POSITIVE.search(text):
            return "L1", "Survey, tutorial, or introductory material — accessible to beginners."
        if paper_type in ("survey", "tutorial") and not _L3_POSITIVE.search(text):
            return "L1", f"Paper type is '{paper_type}' with no advanced technical content."
        if tag_set & _L1_TAGS and not (_L3_POSITIVE.search(text) or _L4_POSITIVE.search(text)):
            matched = sorted(tag_set & _L1_TAGS)
            return "L1", f"Applied NLP/ML topic ({', '.join(matched[:2])}) with no advanced math."

        # ── L4 ────────────────────────────────────────────────────────────────
        if _L4_POSITIVE.search(text):
            m = _L4_POSITIVE.search(text)
            kw = m.group(0) if m else "frontier methods"
            return "L4", f"Requires deep theoretical background — uses {kw.lower()} and related concepts."

        # ── L3 ────────────────────────────────────────────────────────────────
        if _L3_POSITIVE.search(text) or (tag_set & _L3_TAGS):
            if tag_set & _L3_TAGS:
                matched = sorted(tag_set & _L3_TAGS)
                return "L3", f"Advanced topic ({', '.join(matched[:2])}) requiring graduate-level background."
            m = _L3_POSITIVE.search(text)
            kw = m.group(0) if m else "advanced methods"
            return "L3", f"Uses {kw.lower()} — requires solid ML/DL background."

        # ── L2 default ────────────────────────────────────────────────────────
        return "L2", "Intermediate: suitable for readers with undergraduate ML/NLP background."
