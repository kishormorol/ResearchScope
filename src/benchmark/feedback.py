"""Turn conformance findings into feedback an author can act on.

A percentile on its own ("citation_density: p3") tells an author nothing. The
phrasings below name the venue, state what the draft does, state what the
venue's papers do, and leave the judgement to the author — the benchmark
reports a departure from the norm, never a verdict on whether the paper is
good. That distinction matters: the corpus contains only accepted papers, so
"unusual for this venue" is a claim the data supports and "this is wrong" is
not.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.benchmark.reference import Finding

# feature -> (what it measures, unit phrasing, why an author should care when
# it is below / above the venue band).
_PHRASING: dict[str, tuple[str, str, str, str]] = {
    "n_words": (
        "length", "words",
        "Shorter than almost every {venue} {section}. Reviewers may read it as "
        "under-developed — check whether a contribution or result is going unstated.",
        "Longer than almost every {venue} {section}. Consider whether some of it "
        "belongs in a later section.",
    ),
    "citation_density": (
        "citation density", "citations per 100 words",
        "Cites far less than a typical {venue} {section}. Reviewers commonly read "
        "a thin {section} as insufficient engagement with prior art.",
        "Cites far more densely than a typical {venue} {section}. Dense citation "
        "can crowd out your own argument.",
    ),
    "numeric_sentence_ratio": (
        "quantitative density", "fraction of sentences containing a number",
        "Fewer sentences carry numbers than in a typical {venue} {section}. "
        "Quantified claims are what reviewers check first.",
        "More numeric than a typical {venue} {section} — check that the numbers "
        "are interpreted, not only reported.",
    ),
    "hedge_density": (
        "hedging", "hedge words per 100 words",
        "Hedges less than a typical {venue} {section}. Unqualified claims invite "
        "reviewers to look for the counterexample.",
        "Hedges more than a typical {venue} {section}. Heavy hedging can read as "
        "low confidence in your own result.",
    ),
    "booster_density": (
        "claim strength", "intensifiers per 100 words",
        "Uses fewer emphatic claim words than a typical {venue} {section}.",
        "Uses more emphatic claim words than a typical {venue} {section}. "
        "Reviewers tend to discount prose that asserts significance rather than "
        "showing it.",
    ),
    "first_person_density": (
        "authorial voice", "first-person markers per 100 words",
        "Uses first person less than a typical {venue} {section}; the contribution "
        "may read as less clearly yours.",
        "Uses first person more than a typical {venue} {section}.",
    ),
    "connective_density": (
        "discourse connectives", "connectives per 100 words",
        "Uses fewer explicit connectives than a typical {venue} {section}; the "
        "argument may be harder to follow.",
        "Uses more connectives than a typical {venue} {section}.",
    ),
    "mean_sentence_words": (
        "sentence length", "words per sentence",
        "Sentences are shorter than a typical {venue} {section}.",
        "Sentences are longer than a typical {venue} {section}, which can cost "
        "readability.",
    ),
    "figure_ref_density": (
        "figure and table references", "references per 100 words",
        "Refers to figures and tables less than a typical {venue} {section}.",
        "Refers to figures and tables more than a typical {venue} {section}.",
    ),
    "equation_ref_density": (
        "formal notation", "equation references per 100 words",
        "Uses less formal notation than a typical {venue} {section}.",
        "Uses more formal notation than a typical {venue} {section}.",
    ),
    "type_token_ratio": (
        "lexical variety", "unique-word ratio",
        "Repeats vocabulary more than a typical {venue} {section}.",
        "Uses more varied vocabulary than a typical {venue} {section}.",
    ),
    "n_sentences": (
        "sentence count", "sentences",
        "Fewer sentences than a typical {venue} {section}.",
        "More sentences than a typical {venue} {section}.",
    ),
    "n_paragraphs": (
        "paragraph count", "paragraphs",
        "Fewer paragraphs than a typical {venue} {section}.",
        "More paragraphs than a typical {venue} {section}.",
    ),
    "sentence_len_cv": (
        "sentence rhythm", "variation in sentence length",
        "Sentence lengths are more uniform than a typical {venue} {section}, "
        "which can read as monotonous.",
        "Sentence lengths vary more than a typical {venue} {section}.",
    ),
    "mean_word_chars": (
        "word length", "characters per word",
        "Uses shorter words than a typical {venue} {section}.",
        "Uses longer words than a typical {venue} {section}.",
    ),
    "acronym_density": (
        "acronym use", "acronyms per 100 words",
        "Uses fewer acronyms than a typical {venue} {section}.",
        "Uses more acronyms than a typical {venue} {section} — each unfamiliar "
        "one costs the reader.",
    ),
}

_SECTION_LABEL = {
    "abstract": "abstract",
    "introduction": "introduction",
    "related_work": "related work section",
    "method": "method section",
    "experiments": "experiments section",
    "results": "results section",
    "conclusion": "conclusion",
}


@dataclass
class Feedback:
    feature: str
    label: str
    message: str
    your_value: float
    venue_median: float
    venue_range: tuple[float, float]
    percentile: float
    unit: str


def explain(finding: Finding, venue: str, section: str) -> Feedback | None:
    """Render one finding as author-facing feedback, or None if unphrased."""
    entry = _PHRASING.get(finding.feature)
    if entry is None:
        return None
    label, unit, below_msg, above_msg = entry
    template = below_msg if finding.direction == "below" else above_msg
    section_label = _SECTION_LABEL.get(section, section)
    return Feedback(
        feature=finding.feature,
        label=label,
        message=template.format(venue=venue, section=section_label),
        your_value=finding.value,
        venue_median=finding.venue_median,
        venue_range=(finding.venue_low, finding.venue_high),
        percentile=finding.percentile,
        unit=unit,
    )


def explain_all(scored: dict) -> list[Feedback]:
    """Render every finding from `score_section`, most extreme first."""
    venue, section = scored["venue"], scored["section"]
    out = [explain(f, venue, section) for f in scored["findings"]]
    return [f for f in out if f is not None]
