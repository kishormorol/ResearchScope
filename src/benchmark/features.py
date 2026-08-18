"""
T1 surface and structural features for a single paper section.

Every feature here is computable from the section text alone — no parsing of
the reference list, no model inference — so the whole 76k-paper journal corpus
can be featurised from abstracts today, and body sections as GROBID output
lands. Features are expressed as *densities* (per 100 words) wherever the raw
count would otherwise just re-encode section length, so that a long Related
Work and a short one remain comparable.

Sentence splitting is regex-based rather than nltk/spacy on purpose: it keeps
the extractor dependency-free so it runs identically in CI and in the API
process, and scientific abbreviations ("et al.", "Fig.", "vs.") are the only
hard cases, which the guard list below covers.
"""
from __future__ import annotations

import re
from statistics import mean, pstdev

# ── Lexicons ────────────────────────────────────────────────────────────────

# Epistemic hedges: markers of qualified claims. Reviewers read too few as
# overclaiming and too many as a paper unsure of its own result.
_HEDGES = frozenset("""
may might could would possibly perhaps probably likely unlikely suggest
suggests suggested indicate indicates appear appears seem seems tend tends
assume assumed presumably arguably relatively somewhat fairly potential
potentially generally typically often usually sometimes largely partially
""".split())

# Boosters: strong-claim intensifiers, the counterweight to hedging.
_BOOSTERS = frozenset("""
significantly substantially dramatically markedly considerably notably
clearly obviously evidently undoubtedly definitely certainly strongly
consistently remarkably drastically vastly greatly novel first new
unprecedented state-of-the-art outperforms surpasses
""".split())

# Discourse connectives: explicit argument structure.
_CONNECTIVES = frozenset("""
however therefore thus hence moreover furthermore nevertheless nonetheless
consequently additionally conversely although though whereas while despite
because since accordingly overall finally specifically particularly instead
""".split())

# First-person markers: authorial presence, which varies sharply by venue.
_FIRST_PERSON = frozenset("we our us ours ourselves".split())

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")
# Abbreviations that must not end a sentence.
_ABBREV = re.compile(
    r"\b(et al|e\.g|i\.e|cf|vs|Fig|Figs|Eq|Eqs|Sec|Tab|Ref|Refs|approx|resp"
    r"|Dr|Prof|Inc|Ltd|St|No|pp|Vol)\.$",
    re.IGNORECASE,
)

# Citation forms: numeric [12] / [1, 2] and author-year (Smith et al., 2020).
_CITE_NUMERIC = re.compile(r"\[\s*\d+(?:\s*[-–,]\s*\d+)*\s*\]")
_CITE_AUTHOR_YEAR = re.compile(
    r"\((?:[^()]{0,80}?)\b(1[89]|20)\d{2}[a-z]?\b[^()]{0,40}?\)"
)
_CITE_NARRATIVE = re.compile(
    r"\b[A-Z][A-Za-z\-']+\s+(?:et al\.|and\s+[A-Z][A-Za-z\-']+)\s*\(\s*\d{4}"
)

_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?\s*(?:%|×|x\b)?")
_ACRONYM = re.compile(r"\b[A-Z]{2,6}s?\b")
_FIG_REF = re.compile(r"\b(?:fig(?:ure)?s?|tab(?:le)?s?)\.?\s*\d+", re.IGNORECASE)
_EQ_REF = re.compile(r"\b(?:eq(?:uation)?s?)\.?\s*[\d(]|\$[^$]+\$", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z][A-Za-z\-']+")

FEATURE_NAMES: tuple[str, ...] = (
    "n_words",
    "n_sentences",
    "mean_sentence_words",
    "sentence_len_cv",
    "n_paragraphs",
    "mean_word_chars",
    "type_token_ratio",
    "citation_density",
    "numeric_sentence_ratio",
    "hedge_density",
    "booster_density",
    "connective_density",
    "first_person_density",
    "acronym_density",
    "figure_ref_density",
    "equation_ref_density",
)


def split_sentences(text: str) -> list[str]:
    """Split into sentences, keeping scientific abbreviations intact."""
    if not text or not text.strip():
        return []
    raw = _SENT_SPLIT.split(text.strip())
    out: list[str] = []
    for piece in raw:
        # Re-join a fragment whose predecessor ended on a known abbreviation.
        if out and _ABBREV.search(out[-1]):
            out[-1] = f"{out[-1]} {piece}"
        else:
            out.append(piece)
    return [s.strip() for s in out if s.strip()]


def count_citations(text: str) -> int:
    """Citation instances, counting bracket groups and author-year forms.

    Spans are merged before counting: a narrative citation like
    "Smith et al. (2020)" is matched by both the narrative and the
    author-year pattern, and must count once, not twice.
    """
    spans: list[tuple[int, int]] = []
    for pattern in (_CITE_NUMERIC, _CITE_AUTHOR_YEAR, _CITE_NARRATIVE):
        spans.extend(m.span() for m in pattern.finditer(text))
    if not spans:
        return 0
    spans.sort()
    count = 1
    end = spans[0][1]
    for start, stop in spans[1:]:
        if start >= end:          # disjoint -> a distinct citation
            count += 1
            end = stop
        else:                     # overlapping -> same citation
            end = max(end, stop)
    return count


def _density(count: int, n_words: int) -> float:
    """Occurrences per 100 words."""
    return float(round(100.0 * count / n_words, 4)) if n_words else 0.0


def extract_features(text: str) -> dict[str, float]:
    """Return the T1 feature vector for one section's text.

    Returns zeros for every feature on empty input rather than raising, so a
    paper missing a section still yields a well-formed row.
    """
    if not text or not text.strip():
        return dict.fromkeys(FEATURE_NAMES, 0.0)

    sentences = split_sentences(text)
    words = _WORD.findall(text)
    lowered = [w.lower() for w in words]
    n_words = len(words)

    sent_lens = [len(_WORD.findall(s)) for s in sentences] or [0]
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]

    numeric_sentences = sum(1 for s in sentences if _NUMBER.search(s))

    return {
        "n_words": float(n_words),
        "n_sentences": float(len(sentences)),
        "mean_sentence_words": (
            float(round(mean(sent_lens), 3)) if sent_lens else 0.0
        ),
        # Rhythm: how uniform the sentence lengths are. Near-zero reads as
        # monotonous, very high as uneven pacing.
        "sentence_len_cv": (
            float(round(pstdev(sent_lens) / mean(sent_lens), 4))
            if len(sent_lens) > 1 and mean(sent_lens) else 0.0
        ),
        "n_paragraphs": float(len(paragraphs)),
        "mean_word_chars": (
            float(round(mean(len(w) for w in words), 3)) if words else 0.0
        ),
        "type_token_ratio": (
            float(round(len(set(lowered)) / n_words, 4)) if n_words else 0.0
        ),
        "citation_density": _density(count_citations(text), n_words),
        "numeric_sentence_ratio": (
            float(round(numeric_sentences / len(sentences), 4)) if sentences else 0.0
        ),
        "hedge_density": _density(sum(w in _HEDGES for w in lowered), n_words),
        "booster_density": _density(sum(w in _BOOSTERS for w in lowered), n_words),
        "connective_density": _density(
            sum(w in _CONNECTIVES for w in lowered), n_words
        ),
        "first_person_density": _density(
            sum(w in _FIRST_PERSON for w in lowered), n_words
        ),
        "acronym_density": _density(len(_ACRONYM.findall(text)), n_words),
        "figure_ref_density": _density(len(_FIG_REF.findall(text)), n_words),
        "equation_ref_density": _density(len(_EQ_REF.findall(text)), n_words),
    }
