"""
Author / Lab / University aggregation module.

Given a list of scored Papers, this module builds:
  - Author objects with full momentum scores
  - Lab objects inferred from affiliation strings
  - University objects inferred from affiliation strings
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from src.normalization.schema import Author, Lab, Paper, University
from src.scoring.scorer import AuthorMomentumScorer

_CURRENT_YEAR = datetime.now(timezone.utc).year


# ── Name normalisation ────────────────────────────────────────────────────────

def _author_slug(name: str) -> str:
    return re.sub(r"[^\w]", "_", name.strip().lower())


def _org_slug(name: str) -> str:
    return re.sub(r"[^\w]", "_", name.strip().lower()).strip("_")


# ── University keyword mapping ────────────────────────────────────────────────
# Maps a keyword found in affiliation string → canonical university name

_UNI_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"stanford",           re.IGNORECASE), "Stanford University"),
    (re.compile(r"mit\b|massachusetts institute of tech", re.IGNORECASE), "MIT"),
    (re.compile(r"\bcmu\b|carnegie mellon",re.IGNORECASE), "Carnegie Mellon University"),
    (re.compile(r"berkeley",           re.IGNORECASE), "UC Berkeley"),
    (re.compile(r"oxford",             re.IGNORECASE), "University of Oxford"),
    (re.compile(r"cambridge",          re.IGNORECASE), "University of Cambridge"),
    (re.compile(r"toronto",            re.IGNORECASE), "University of Toronto"),
    (re.compile(r"montreal|mila",      re.IGNORECASE), "Université de Montréal / MILA"),
    (re.compile(r"new york university|nyu\b", re.IGNORECASE), "New York University"),
    (re.compile(r"columbia",           re.IGNORECASE), "Columbia University"),
    (re.compile(r"washington",         re.IGNORECASE), "University of Washington"),
    (re.compile(r"princeton",          re.IGNORECASE), "Princeton University"),
    (re.compile(r"harvard",            re.IGNORECASE), "Harvard University"),
    (re.compile(r"yale",               re.IGNORECASE), "Yale University"),
    (re.compile(r"edinburgh",          re.IGNORECASE), "University of Edinburgh"),
    (re.compile(r"eth zurich|eth zürich", re.IGNORECASE), "ETH Zurich"),
    (re.compile(r"tsinghua",           re.IGNORECASE), "Tsinghua University"),
    (re.compile(r"peking university|pku\b", re.IGNORECASE), "Peking University"),
    (re.compile(r"chinese university of hong kong|cuhk\b", re.IGNORECASE), "CUHK"),
    (re.compile(r"national university of singapore|nus\b", re.IGNORECASE), "NUS"),
    (re.compile(r"stony brook|sbu\b",  re.IGNORECASE), "Stony Brook University"),
    (re.compile(r"illinois|uiuc\b",    re.IGNORECASE), "University of Illinois"),
    (re.compile(r"michigan",           re.IGNORECASE), "University of Michigan"),
    (re.compile(r"cornell",            re.IGNORECASE), "Cornell University"),
    (re.compile(r"maryland",           re.IGNORECASE), "University of Maryland"),
    (re.compile(r"georgia tech",       re.IGNORECASE), "Georgia Institute of Technology"),
    (re.compile(r"johns hopkins",      re.IGNORECASE), "Johns Hopkins University"),
    (re.compile(r"ucla\b|los angeles", re.IGNORECASE), "UCLA"),
    (re.compile(r"ucsd\b|san diego",   re.IGNORECASE), "UC San Diego"),
    (re.compile(r"usc\b|southern california", re.IGNORECASE), "University of Southern California"),
]

# Lab / industry patterns
_LAB_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"google.*brain|google brain",   re.IGNORECASE), "Google Brain"),
    (re.compile(r"google.*deepmind|deepmind",    re.IGNORECASE), "DeepMind"),
    (re.compile(r"google.*research|google inc",  re.IGNORECASE), "Google Research"),
    (re.compile(r"openai",                       re.IGNORECASE), "OpenAI"),
    (re.compile(r"anthropic",                    re.IGNORECASE), "Anthropic"),
    (re.compile(r"meta.*ai|fair\b|facebook.*ai", re.IGNORECASE), "Meta AI (FAIR)"),
    (re.compile(r"microsoft.*research",          re.IGNORECASE), "Microsoft Research"),
    (re.compile(r"amazon.*aws|amazon.*alexa",    re.IGNORECASE), "Amazon AWS / Alexa AI"),
    (re.compile(r"apple.*ai|apple.*ml",          re.IGNORECASE), "Apple ML"),
    (re.compile(r"nvidia.*research",             re.IGNORECASE), "NVIDIA Research"),
    (re.compile(r"hugging face",                 re.IGNORECASE), "Hugging Face"),
    (re.compile(r"allen.*institute|ai2\b",       re.IGNORECASE), "Allen Institute for AI (AI2)"),
    (re.compile(r"ibm.*research",                re.IGNORECASE), "IBM Research"),
    (re.compile(r"salesforce.*research",         re.IGNORECASE), "Salesforce Research"),
    (re.compile(r"baidu.*research",              re.IGNORECASE), "Baidu Research"),
    (re.compile(r"tencent.*ai",                  re.IGNORECASE), "Tencent AI Lab"),
    (re.compile(r"alibaba.*damo",                re.IGNORECASE), "Alibaba DAMO"),
    (re.compile(r"intel.*labs",                  re.IGNORECASE), "Intel Labs"),
]


def _match_university(text: str) -> str | None:
    for pattern, name in _UNI_PATTERNS:
        if pattern.search(text):
            return name
    return None


def _match_lab(text: str) -> str | None:
    for pattern, name in _LAB_PATTERNS:
        if pattern.search(text):
            return name
    return None


# ── Main aggregator ───────────────────────────────────────────────────────────

class Aggregator:
    """Build Author, Lab, and University objects from a list of Papers."""

    def __init__(self) -> None:
        self._momentum_scorer = AuthorMomentumScorer()

    # ── Authors ───────────────────────────────────────────────────────────────

    def build_authors(self, papers: list[Paper]) -> list[Author]:
        author_map: dict[str, Author] = {}
        papers_by_id: dict[str, Paper] = {p.id: p for p in papers}

        for paper in papers:
            for name in paper.authors:
                aid = _author_slug(name)
                if not aid:
                    continue
                if aid not in author_map:
                    author_map[aid] = Author(author_id=aid, name=name)
                author = author_map[aid]

                if paper.id not in author.paper_ids:
                    author.paper_ids.append(paper.id)
                if _CURRENT_YEAR - paper.year <= 2 and paper.id not in author.recent_paper_ids:
                    author.recent_paper_ids.append(paper.id)

                for tag in paper.tags:
                    if tag not in author.topics:
                        author.topics.append(tag)

                venue = paper.venue or ""
                if venue:
                    author.conference_counts[venue] = author.conference_counts.get(venue, 0) + 1

                for aff in paper.affiliations_raw:
                    if aff and aff not in author.affiliations:
                        author.affiliations.append(aff)
                    lab = _match_lab(aff)
                    if lab and _org_slug(lab) not in author.lab_ids:
                        author.lab_ids.append(_org_slug(lab))
                    uni = _match_university(aff)
                    if uni and _org_slug(uni) not in author.university_ids:
                        author.university_ids.append(_org_slug(uni))

        # score momentum
        for author in author_map.values():
            author.topics = author.topics[:10]
            self._momentum_scorer.score(author, papers_by_id)
            author.summary_profile = self._author_profile(author)

        return sorted(author_map.values(), key=lambda a: -len(a.paper_ids))

    @staticmethod
    def _author_profile(author: Author) -> str:
        n = len(author.paper_ids)
        r = len(author.recent_paper_ids)
        topics = ", ".join(author.topics[:3]) if author.topics else "various topics"
        affil = author.affiliations[0] if author.affiliations else ""
        affil_str = f" ({affil})" if affil else ""
        return (
            f"{author.name}{affil_str} has {n} tracked paper{'s' if n != 1 else ''}, "
            f"{r} in the last 2 years. Active in: {topics}. "
            f"Momentum score: {author.momentum_score:.1f}/10."
        )

    # ── Labs ──────────────────────────────────────────────────────────────────

    def build_labs(self, papers: list[Paper]) -> list[Lab]:
        lab_map: dict[str, Lab] = {}

        for paper in papers:
            # Infer labs from affiliations_raw
            aff_labs: list[str] = []
            for aff in paper.affiliations_raw:
                lab = _match_lab(aff)
                if lab:
                    aff_labs.append(lab)

            # Also use lab_ids already set on paper
            for lid in paper.lab_ids:
                if lid not in [_org_slug(l) for l in aff_labs]:
                    aff_labs.append(lid)

            for lab_name in aff_labs:
                lid = _org_slug(lab_name)
                if not lid:
                    continue
                if lid not in lab_map:
                    lab_map[lid] = Lab(lab_id=lid, name=lab_name if not lid.startswith("_") else lid)
                lab = lab_map[lid]

                if paper.id not in lab.paper_ids:
                    lab.paper_ids.append(paper.id)
                if _CURRENT_YEAR - paper.year <= 2 and paper.id not in lab.recent_papers:
                    lab.recent_papers.append(paper.id)
                for tag in paper.tags:
                    if tag not in lab.topics:
                        lab.topics.append(tag)
                for name in paper.authors:
                    if name not in lab.authors:
                        lab.authors.append(name)
                if paper.conference_rank in ("A*",):
                    lab.a_star_output += 1

        for lab in lab_map.values():
            lab.topics = lab.topics[:10]
            lab.momentum_score = self._lab_momentum(lab, papers)
            lab.summary_profile = self._lab_profile(lab)

        return sorted(lab_map.values(), key=lambda l: -len(l.paper_ids))

    @staticmethod
    def _lab_momentum(lab: Lab, papers: list[Paper]) -> float:
        papers_by_id = {p.id: p for p in papers}
        lab_papers = [papers_by_id[pid] for pid in lab.paper_ids if pid in papers_by_id]
        if not lab_papers:
            return 0.0
        recent = sum(1 for p in lab_papers if _CURRENT_YEAR - p.year <= 2)
        a_star = sum(1 for p in lab_papers if p.conference_rank == "A*")
        avg_score = sum(p.paper_score for p in lab_papers) / len(lab_papers)
        raw = recent * 0.5 + (a_star / len(lab_papers)) * 10 * 0.3 + avg_score * 0.2
        return round(min(raw, 10.0), 2)

    @staticmethod
    def _lab_profile(lab: Lab) -> str:
        n = len(lab.paper_ids)
        topics = ", ".join(lab.topics[:3]) if lab.topics else "various areas"
        return (
            f"{lab.name} has {n} tracked paper{'s' if n != 1 else ''}, "
            f"{lab.a_star_output} at A* venues. "
            f"Top topics: {topics}. Momentum: {lab.momentum_score:.1f}/10."
        )

    # ── Universities ──────────────────────────────────────────────────────────

    def build_universities(self, papers: list[Paper]) -> list[University]:
        uni_map: dict[str, University] = {}

        for paper in papers:
            unis: list[str] = []
            for aff in paper.affiliations_raw:
                uni = _match_university(aff)
                if uni:
                    unis.append(uni)
            for uid in paper.university_ids:
                unis.append(uid)

            for uni_name in set(unis):
                uid = _org_slug(uni_name)
                if not uid:
                    continue
                if uid not in uni_map:
                    uni_map[uid] = University(university_id=uid, name=uni_name)
                u = uni_map[uid]

                if paper.id not in u.papers:
                    u.papers.append(paper.id)
                for tag in paper.tags:
                    if tag not in u.topics:
                        u.topics.append(tag)
                for author_name in paper.authors:
                    if author_name not in u.authors:
                        u.authors.append(author_name)
                venue = paper.venue or ""
                if venue:
                    u.conference_output[venue] = u.conference_output.get(venue, 0) + 1

        for u in uni_map.values():
            u.topics = u.topics[:10]
            u.momentum_score = self._uni_momentum(u, papers)
            u.summary_profile = self._uni_profile(u)

        return sorted(uni_map.values(), key=lambda u: -len(u.papers))

    @staticmethod
    def _uni_momentum(uni: University, papers: list[Paper]) -> float:
        papers_by_id = {p.id: p for p in papers}
        uni_papers = [papers_by_id[pid] for pid in uni.papers if pid in papers_by_id]
        if not uni_papers:
            return 0.0
        recent = sum(1 for p in uni_papers if _CURRENT_YEAR - p.year <= 2)
        raw = min(recent / max(len(uni_papers), 1) * 10.0, 10.0)
        return round(raw, 2)

    @staticmethod
    def _uni_profile(u: University) -> str:
        n = len(u.papers)
        topics = ", ".join(u.topics[:3]) if u.topics else "various areas"
        return (
            f"{u.name} has {n} tracked paper{'s' if n != 1 else ''} "
            f"from {len(u.authors)} tracked author{'s' if len(u.authors) != 1 else ''}. "
            f"Top topics: {topics}."
        )
