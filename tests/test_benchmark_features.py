"""T1 feature extraction: sentence splitting, citation counting, densities."""
from __future__ import annotations

import pytest

from src.benchmark.features import (
    FEATURE_NAMES,
    count_citations,
    extract_features,
    split_sentences,
)


class TestSplitSentences:
    def test_basic(self):
        assert len(split_sentences("One idea. Two ideas. Three.")) == 3

    @pytest.mark.parametrize("text", [
        "Prior work by Smith et al. showed gains. We disagree.",
        "We use BERT, e.g. the base model. It works.",
        "See Fig. 3 for the curve. The trend holds.",
        "Accuracy rose vs. the baseline. That is the claim.",
    ])
    def test_abbreviations_do_not_split(self, text):
        # Each fixture is exactly two sentences despite an internal period.
        assert len(split_sentences(text)) == 2

    def test_empty(self):
        assert split_sentences("") == []
        assert split_sentences("   ") == []


class TestCountCitations:
    @pytest.mark.parametrize("text,expected", [
        ("As shown in [12].", 1),
        ("Prior work [1, 2, 3] and [7].", 2),
        ("Following (Smith et al., 2020).", 1),
        ("Two forms (Jones, 2019) and [4].", 2),
        ("Smith et al. (2020) proposed this.", 1),
        ("No citations at all here.", 0),
    ])
    def test_forms(self, text, expected):
        assert count_citations(text) == expected

    def test_year_alone_is_not_a_citation(self):
        assert count_citations("The 2020 dataset has 50000 rows.") == 0


class TestExtractFeatures:
    def test_returns_every_feature(self):
        f = extract_features("A sentence with content. And another one.")
        assert set(f) == set(FEATURE_NAMES)
        assert all(isinstance(v, float) for v in f.values())

    def test_empty_text_is_all_zeros(self):
        f = extract_features("")
        assert set(f) == set(FEATURE_NAMES)
        assert all(v == 0.0 for v in f.values())

    def test_densities_are_length_invariant(self):
        # The same prose repeated should not change a per-100-word density.
        unit = "We propose a method [1]. It improves results however. "
        one = extract_features(unit)
        ten = extract_features(unit * 10)
        assert one["citation_density"] == pytest.approx(
            ten["citation_density"], rel=0.02
        )
        assert one["hedge_density"] == pytest.approx(ten["hedge_density"], rel=0.02)
        # Raw counts, by contrast, must scale.
        assert ten["n_words"] > 5 * one["n_words"]

    def test_paragraph_counting(self):
        f = extract_features("First para line.\n\nSecond para line.\n\nThird.")
        assert f["n_paragraphs"] == 3.0

    def test_numeric_sentence_ratio(self):
        f = extract_features("We report 3.2% gain. No numbers in this one.")
        assert f["numeric_sentence_ratio"] == pytest.approx(0.5)

    def test_first_person_density_distinguishes_voice(self):
        active = extract_features("We propose our method and we evaluate it.")
        passive = extract_features("A method is proposed and it is evaluated.")
        assert active["first_person_density"] > passive["first_person_density"]
        assert passive["first_person_density"] == 0.0
