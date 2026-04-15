"""
Multi-score system for ResearchScope.

Four independent scores, each with a breakdown dict and a plain-English reason:

1. paper_score       — "what matters"         (0–10)
2. read_first_score  — "what to read first"   (0–10)
3. content_potential — "worth talking about"  (0–10)
4. author momentum   — used by aggregator

All weights come from config/weights.yaml but fall back to hard-coded defaults
so the scorer works without PyYAML installed.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.normalization.schema import Author, Paper

_CURRENT_YEAR = datetime.now(timezone.utc).year

# ── Config helpers ───────────────────────────────────────────────────────────

def _load_weights() -> dict[str, Any]:
    cfg_path = Path(__file__).parent.parent.parent / "config" / "weights.yaml"
    try:
        import yaml  # type: ignore
        with open(cfg_path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        pass
    return {}

_WEIGHTS: dict[str, Any] = _load_weights()

def _w(score_name: str, component: str, default: float) -> float:
    return float((_WEIGHTS.get(score_name) or {}).get(component, default))

def _rank_score(rank: str) -> float:
    table = {"A*": 10.0, "A": 7.5, "B": 5.0, "C": 3.0, "": 0.0}
    return table.get(rank, 0.0)


# ── Novelty keywords ─────────────────────────────────────────────────────────

_NOVELTY_POSITIVE = re.compile(
    r"\b(novel|new|first|propose|introduce|we present|outperform|state.of.the.art|"
    r"sota|surpass|achieve|improve|advance|breakthrough|superior|exceed)\b",
    re.IGNORECASE,
)
_NOVELTY_NEGATIVE = re.compile(
    r"\b(survey|overview|tutorial|review|we compare|we replicate|replication)\b",
    re.IGNORECASE,
)

_FOUNDATIONAL_KWORDS = re.compile(
    r"\b(foundational|seminal|attention is all|bert|transformer|gpt|imagenet|"
    r"resnet|widely used|widely adopted|introduced by|pioneered)\b",
    re.IGNORECASE,
)
_CLARITY_INDICATORS = re.compile(
    r"\b(we propose|we present|in this paper|in this work|we show|we demonstrate|"
    r"our approach|our method|our model|we introduce)\b",
    re.IGNORECASE,
)
_SURPRISE_KWORDS = re.compile(
    r"\b(surprising|unexpected|counter.intuitive|contrary|surprisingly|"
    r"against intuition|puzzle|paradox|we find that|interestingly)\b",
    re.IGNORECASE,
)
_PRACTICAL_KWORDS = re.compile(
    r"\b(deploy|production|real.world|practical|application|industry|"
    r"downstream|benchmark|use case|system|product)\b",
    re.IGNORECASE,
)
_EXPLAIN_KWORDS = re.compile(
    r"\b(simple|intuitive|straightforward|easy to|visuali[zs]|interpretable|"
    r"explainable)\b",
    re.IGNORECASE,
)
_BROAD_KWORDS = re.compile(
    r"\b(general|generaliz|cross.domain|multi.task|zero.shot|few.shot|"
    r"robust|diverse|broad)\b",
    re.IGNORECASE,
)

_HOT_TAGS = {
    "Large Language Models", "Transformer Architectures", "Diffusion Models",
    "Retrieval-Augmented Generation", "Multimodal Learning",
    "Code Generation & Synthesis", "AI Safety & Alignment", "AI Agents & Tool Use",
}


# ── Renowned author list ──────────────────────────────────────────────────────
# Full names only — avoids false positives on common surnames (Chen, Wang, Li…).
# Covers Turing Award winners, lab founders/directors, and seminal paper authors.
# Score: 10 if ≥1 Tier-1 author, 7 if ≥1 Tier-2 author, 4 if ≥1 Tier-3 author.

_RENOWNED_AUTHORS_T1: frozenset[str] = frozenset({
    # Turing Award / field founders
    "Geoffrey Hinton", "Yann LeCun", "Yoshua Bengio",
    # Lab founders / directors with active research output
    "Ilya Sutskever", "Demis Hassabis", "Shane Legg",
    # Seminal paper authors
    "Ian Goodfellow", "Andrej Karpathy", "Alex Krizhevsky",
    "Diederik Kingma", "John Schulman", "Alec Radford",
    "Tom B. Brown", "Jacob Devlin", "Ashish Vaswani",
    "Noam Shazeer", "Niki Parmar", "David Silver",
    "Oriol Vinyals", "Jeff Dean", "Andrew Ng",
    "Fei-Fei Li", "Jürgen Schmidhuber", "Jimmy Lei Ba",
})

_RENOWNED_AUTHORS_T2: frozenset[str] = frozenset({
    "Pieter Abbeel", "Sergey Levine", "Chelsea Finn",
    "Percy Liang", "Christopher Manning", "Dan Jurafsky",
    "Michael I. Jordan", "Trevor Darrell", "Jitendra Malik",
    "Stuart Russell", "Daphne Koller", "Bernhard Schölkopf",
    "Zoubin Ghahramani", "Max Welling", "Hugo Larochelle",
    "Aaron Courville", "Graham Neubig", "Luke Zettlemoyer",
    "Jason Weston", "Kyunghyun Cho", "Richard Socher",
    "Thomas Wolf", "Sebastian Ruder", "Roger Grosse",
    "Prafulla Dhariwal", "Samy Bengio", "Noam Brown",
    "Jakob Foerster", "Koray Kavukcuoglu", "Raia Hadsell",
    "Nando de Freitas", "Marc Lanctot",
})

_RENOWNED_AUTHORS_T3: frozenset[str] = frozenset({
    "Mike Lewis", "Omer Levy", "Veselin Stoyanov",
    "Kenton Lee", "Ming-Wei Chang", "Tim Salimans",
    "Alex Graves", "Kaiming He", "Ross Girshick",
    "Tomas Mikolov", "Quoc V. Le", "Barret Zoph",
    "Lukasz Kaiser", "Sam Bowman", "Yejin Choi",
    "Noah A. Smith", "Danqi Chen", "Regina Barzilay",
    "Tommi Jaakkola", "Ruslan Salakhutdinov", "George Dahl",
    "Laurent Dinh", "Jimmy Ba", "Vinod Nair",
    "Dragomir Radev", "Leslie Kaelbling",
})

# Lowercased for case-insensitive matching
_T1_AUTHOR_LOWER = frozenset(n.lower() for n in _RENOWNED_AUTHORS_T1)
_T2_AUTHOR_LOWER = frozenset(n.lower() for n in _RENOWNED_AUTHORS_T2)
_T3_AUTHOR_LOWER = frozenset(n.lower() for n in _RENOWNED_AUTHORS_T3)


# ── Institution prestige tiers ────────────────────────────────────────────────
# Tier 1 (score 10): frontier AI labs and top-3 CS universities
# Tier 2 (score 7):  major industry research + elite universities
# Tier 3 (score 4):  strong universities and known research orgs
# Detection: checked against affiliations_raw first; falls back to abstract scan.

_TIER1_INSTITUTIONS = re.compile(
    r"\b(openai|deepmind|google\s*(?:brain|research|deepmind)?|anthropic|"
    r"meta\s*(?:ai|research|fair)?|microsoft\s*research|mit\b|"
    r"stanford|carnegie\s*mellon|cmu\b)\b",
    re.IGNORECASE,
)
_TIER2_INSTITUTIONS = re.compile(
    r"\b(berkeley|caltech|cambridge|oxford|princeton|harvard|"
    r"toronto|montreal|mila\b|vector\s*institute|"
    r"nvidia\s*research|apple\s*(?:ml|research)?|amazon\s*(?:science|research)?|"
    r"ibm\s*research|samsung\s*research|adobe\s*research|"
    r"eth\s*zurich|epfl|tsinghua|peking\s*university|pku\b|"
    r"national\s*university\s*of\s*singapore|nus\b)\b",
    re.IGNORECASE,
)
_TIER3_INSTITUTIONS = re.compile(
    r"\b(yale|columbia|cornell|michigan|ucsd|ucla|usc|georgia\s*tech|"
    r"university\s*of\s*washington|uw\b|edinburgh|imperial\s*college|"
    r"bytedance|tencent\s*(?:ai|research)?|baidu\s*(?:research)?|"
    r"huawei\s*(?:noah|research)?|alibaba\s*(?:damo)?|jd\.ai|"
    r"kakao|naver|kaist\b|postech|technion|inria\b|max\s*planck)\b",
    re.IGNORECASE,
)


# ── PaperScorer ───────────────────────────────────────────────────────────────

class PaperScorer:
    """Compute all paper scores and attach breakdowns."""

    def score(self, paper: Paper) -> Paper:
        paper.paper_score = self._paper_score(paper)
        paper.read_first_score = self._read_first_score(paper)
        paper.content_potential_score = self._content_potential_score(paper)
        paper.interestingness_score = round(
            0.5 * paper.paper_score + 0.5 * paper.content_potential_score, 2
        )
        return paper

    # ── 1. Paper score ────────────────────────────────────────────────────────

    def _paper_score(self, paper: Paper) -> float:
        text = f"{paper.title} {paper.abstract}"

        recency      = self._recency(paper.year)
        novelty      = self._novelty(text)
        quality      = self._quality_hint(paper)
        completeness = self._completeness(paper)
        inst_prestige   = self._institution_prestige(paper)
        author_prestige = self._author_prestige(paper)

        w_r  = _w("paper_score", "recency",            0.28)
        w_n  = _w("paper_score", "novelty",             0.22)
        w_q  = _w("paper_score", "quality_hint",        0.18)
        w_c  = _w("paper_score", "completeness",        0.07)
        w_ip = _w("paper_score", "institution_prestige", 0.15)
        w_ap = _w("paper_score", "author_prestige",      0.10)

        raw = (recency * w_r + novelty * w_n + quality * w_q
               + completeness * w_c + inst_prestige * w_ip + author_prestige * w_ap)
        score = round(min(max(raw, 0.0), 10.0), 2)

        paper.score_breakdown["paper_score"] = {
            "score": score,
            "recency": round(recency, 2),
            "novelty": round(novelty, 2),
            "quality_hint": round(quality, 2),
            "completeness": round(completeness, 2),
            "institution_prestige": round(inst_prestige, 2),
            "author_prestige": round(author_prestige, 2),
            "reason": self._paper_reason(score, recency, novelty, quality, inst_prestige, author_prestige),
        }
        return score

    @staticmethod
    def _paper_reason(
        score: float, recency: float, novelty: float, quality: float,
        inst_prestige: float = 0.0, author_prestige: float = 0.0,
    ) -> str:
        parts = []
        if recency >= 7:
            parts.append("recently published")
        elif recency <= 2:
            parts.append("older work")
        if novelty >= 7:
            parts.append("strong novelty signals")
        elif novelty <= 3:
            parts.append("limited novelty language")
        if quality >= 7:
            parts.append("high-quality venue / citation count")
        if author_prestige >= 8:
            parts.append("renowned author")
        elif inst_prestige >= 8:
            parts.append("top-tier lab or university")
        elif inst_prestige >= 5 or author_prestige >= 5:
            parts.append("reputable institution")
        if not parts:
            parts.append("average on all dimensions")
        return f"Paper scores {score:.1f}/10 — {', '.join(parts)}."

    # ── 2. Read-first score ───────────────────────────────────────────────────

    def _read_first_score(self, paper: Paper) -> float:
        text = f"{paper.title} {paper.abstract}"

        clarity      = self._clarity(paper.abstract)
        foundational = self._foundational(text)
        accessibility = self._accessibility(paper.difficulty_level)
        topic_centrality = self._topic_centrality(paper.tags)

        w_cl = _w("read_first_score", "clarity",         0.30)
        w_fo = _w("read_first_score", "foundational",    0.25)
        w_ac = _w("read_first_score", "accessibility",   0.25)
        w_tc = _w("read_first_score", "topic_centrality", 0.20)

        raw = (clarity * w_cl + foundational * w_fo
               + accessibility * w_ac + topic_centrality * w_tc)
        score = round(min(max(raw, 0.0), 10.0), 2)

        paper.score_breakdown["read_first_score"] = {
            "score": score,
            "clarity": round(clarity, 2),
            "foundational": round(foundational, 2),
            "accessibility": round(accessibility, 2),
            "topic_centrality": round(topic_centrality, 2),
            "reason": self._read_reason(score, clarity, foundational, accessibility),
        }
        return score

    @staticmethod
    def _read_reason(score: float, clarity: float, foundational: float, access: float) -> str:
        parts = []
        if clarity >= 7:
            parts.append("well-written abstract")
        if foundational >= 6:
            parts.append("foundational concepts")
        if access >= 7:
            parts.append("accessible for most readers")
        elif access <= 3:
            parts.append("requires significant background")
        if not parts:
            parts.append("average readability and accessibility")
        return f"Read-first {score:.1f}/10 — {', '.join(parts)}."

    # ── 3. Content potential score ────────────────────────────────────────────

    def _content_potential_score(self, paper: Paper) -> float:
        text = f"{paper.title} {paper.abstract}"

        surprise    = self._surprise(text)
        practical   = self._practical(text)
        explain     = self._explainability(text)
        broad       = self._broad_relevance(text)
        trend       = self._trend_alignment(paper.tags)

        w_su = _w("content_potential_score", "surprise",        0.25)
        w_pr = _w("content_potential_score", "practical_value", 0.25)
        w_ex = _w("content_potential_score", "explainability",  0.20)
        w_br = _w("content_potential_score", "broad_relevance", 0.20)
        w_tr = _w("content_potential_score", "trend_alignment", 0.10)

        raw = (surprise * w_su + practical * w_pr + explain * w_ex
               + broad * w_br + trend * w_tr)
        score = round(min(max(raw, 0.0), 10.0), 2)

        paper.score_breakdown["content_potential"] = {
            "score": score,
            "surprise": round(surprise, 2),
            "practical_value": round(practical, 2),
            "explainability": round(explain, 2),
            "broad_relevance": round(broad, 2),
            "trend_alignment": round(trend, 2),
            "reason": self._content_reason(score, surprise, practical, trend),
        }
        paper.content_potential_score = score
        return score

    @staticmethod
    def _content_reason(score: float, surprise: float, practical: float, trend: float) -> str:
        parts = []
        if surprise >= 6:
            parts.append("surprising or unexpected results")
        if practical >= 6:
            parts.append("clear practical applications")
        if trend >= 7:
            parts.append("hot topic right now")
        if not parts:
            parts.append("solid but not especially viral")
        return f"Content potential {score:.1f}/10 — {', '.join(parts)}."

    # ── Component helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _recency(year: int) -> float:
        if not year:
            return 0.0
        age = _CURRENT_YEAR - year
        if age < 0:
            return 10.0
        if age >= 10:
            return 0.0
        return round(10.0 * (1 - age / 10), 2)

    @staticmethod
    def _novelty(text: str) -> float:
        pos = len(_NOVELTY_POSITIVE.findall(text))
        neg = len(_NOVELTY_NEGATIVE.findall(text))
        raw = min(pos * 1.5, 10.0) - min(neg * 2.0, 5.0)
        return round(max(raw, 0.0), 2)

    @staticmethod
    def _quality_hint(paper: Paper) -> float:
        rank_s = _rank_score(paper.conference_rank)
        cite_s = min(10.0 * math.log1p(paper.citations) / math.log1p(1000), 10.0) if paper.citations else 0.0
        # if no conference rank, citations dominate
        if rank_s == 0:
            return round(cite_s, 2)
        return round(rank_s * 0.7 + cite_s * 0.3, 2)

    @staticmethod
    def _author_prestige(paper: Paper) -> float:
        """
        Score 0–10 based on whether any author is in the curated renowned-author list.
        Uses full-name matching (case-insensitive) to avoid false positives on
        common surnames like Chen, Wang, Li.
        """
        authors_lower = {a.lower() for a in (paper.authors or [])}
        if authors_lower & _T1_AUTHOR_LOWER:
            return 10.0
        if authors_lower & _T2_AUTHOR_LOWER:
            return 7.0
        if authors_lower & _T3_AUTHOR_LOWER:
            return 4.0
        return 0.0

    @staticmethod
    def _institution_prestige(paper: Paper) -> float:
        """
        Score 0–10 based on author affiliations or abstract mentions of known
        high-prestige institutions.  Checks affiliations_raw first (populated
        when Semantic Scholar returns affiliation data); falls back to scanning
        the abstract so papers that mention their lab still get credit.
        """
        # Build a single string to search: affiliations > abstract fallback
        sources = list(paper.affiliations_raw or [])
        if not sources:
            sources = [paper.abstract or ""]

        combined = " ".join(sources)
        if _TIER1_INSTITUTIONS.search(combined):
            return 10.0
        if _TIER2_INSTITUTIONS.search(combined):
            return 7.0
        if _TIER3_INSTITUTIONS.search(combined):
            return 4.0
        return 0.0

    @staticmethod
    def _completeness(paper: Paper) -> float:
        score = 0.0
        if paper.abstract: score += 3.0
        if paper.authors:  score += 2.0
        if paper.pdf_url:  score += 1.0
        if paper.summary:  score += 1.5
        if paper.tags:     score += 1.5
        if paper.limitations: score += 1.0
        return round(min(score, 10.0), 2)

    @staticmethod
    def _clarity(abstract: str) -> float:
        words = len(abstract.split()) if abstract else 0
        structure = len(_CLARITY_INDICATORS.findall(abstract))
        word_score = min(words / 25.0, 5.0)
        struct_score = min(structure * 1.5, 5.0)
        return round(word_score + struct_score, 2)

    @staticmethod
    def _foundational(text: str) -> float:
        hits = len(_FOUNDATIONAL_KWORDS.findall(text))
        return round(min(hits * 3.0, 10.0), 2)

    @staticmethod
    def _accessibility(difficulty_level: str) -> float:
        return {"L1": 10.0, "L2": 7.0, "L3": 4.0, "L4": 1.5}.get(difficulty_level, 5.0)

    @staticmethod
    def _topic_centrality(tags: list[str]) -> float:
        hot = sum(1 for t in tags if t in _HOT_TAGS)
        return round(min(hot * 2.5, 10.0), 2)

    @staticmethod
    def _surprise(text: str) -> float:
        hits = len(_SURPRISE_KWORDS.findall(text))
        return round(min(hits * 3.0, 10.0), 2)

    @staticmethod
    def _practical(text: str) -> float:
        hits = len(_PRACTICAL_KWORDS.findall(text))
        return round(min(hits * 1.5, 10.0), 2)

    @staticmethod
    def _explainability(text: str) -> float:
        hits = len(_EXPLAIN_KWORDS.findall(text))
        return round(min(hits * 2.0, 10.0), 2)

    @staticmethod
    def _broad_relevance(text: str) -> float:
        hits = len(_BROAD_KWORDS.findall(text))
        return round(min(hits * 1.5, 10.0), 2)

    @staticmethod
    def _trend_alignment(tags: list[str]) -> float:
        hot = sum(1 for t in tags if t in _HOT_TAGS)
        return round(min(hot * 2.5, 10.0), 2)


# ── AuthorMomentumScorer ──────────────────────────────────────────────────────

class AuthorMomentumScorer:
    """Score an author's momentum given their papers."""

    def score(self, author: Author, papers_by_id: dict[str, Paper]) -> Author:
        author_papers = [papers_by_id[pid] for pid in author.paper_ids if pid in papers_by_id]
        if not author_papers:
            author.momentum_score = 0.0
            return author

        current_year = _CURRENT_YEAR
        recent = [p for p in author_papers if current_year - p.year <= 2]
        prior  = [p for p in author_papers if 2 < current_year - p.year <= 4]

        # components
        recent_output    = min(len(recent) * 1.5, 10.0)
        avg_quality      = (sum(p.paper_score for p in author_papers) / len(author_papers)) if author_papers else 0.0
        acceleration     = min((len(recent) / max(len(prior), 1)) * 5.0, 10.0)
        topic_strength   = self._topic_strength(author_papers)
        conf_strength    = self._conference_strength(author_papers)

        w_ro = _w("author_momentum", "recent_output",       0.30)
        w_aq = _w("author_momentum", "avg_quality",         0.25)
        w_ac = _w("author_momentum", "acceleration",        0.20)
        w_ts = _w("author_momentum", "topic_strength",      0.15)
        w_cs = _w("author_momentum", "conference_strength", 0.10)

        raw = (recent_output * w_ro + avg_quality * w_aq + acceleration * w_ac
               + topic_strength * w_ts + conf_strength * w_cs)
        author.momentum_score = round(min(max(raw, 0.0), 10.0), 2)
        author.avg_paper_score = round(avg_quality, 2)
        author.momentum_breakdown = {
            "recent_output": round(recent_output, 2),
            "avg_quality": round(avg_quality, 2),
            "acceleration": round(acceleration, 2),
            "topic_strength": round(topic_strength, 2),
            "conference_strength": round(conf_strength, 2),
        }
        return author

    @staticmethod
    def _topic_strength(papers: list[Paper]) -> float:
        hot_count = sum(1 for p in papers for t in p.tags if t in _HOT_TAGS)
        return round(min(hot_count * 0.8, 10.0), 2)

    @staticmethod
    def _conference_strength(papers: list[Paper]) -> float:
        if not papers:
            return 0.0
        ranked = sum(1 for p in papers if p.conference_rank in ("A*", "A"))
        return round(min(ranked / len(papers) * 10.0, 10.0), 2)
