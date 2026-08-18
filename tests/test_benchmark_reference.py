"""Reference distributions: percentile placement, banding, tier pooling."""
from __future__ import annotations

import random

import pytest

from src.benchmark.features import FEATURE_NAMES
from src.benchmark.reference import (
    Reference,
    ReferenceSet,
    fit_corpus,
    score_section,
)


def _vec(**overrides) -> dict[str, float]:
    v = dict.fromkeys(FEATURE_NAMES, 0.0)
    v.update(overrides)
    return v


def _population(n=500, mu=2.0, sigma=0.5, seed=0) -> list[dict[str, float]]:
    rng = random.Random(seed)
    return [_vec(citation_density=rng.gauss(mu, sigma),
                 n_words=rng.gauss(200, 30)) for _ in range(n)]


class TestPercentile:
    def setup_method(self):
        self.ref = Reference.fit("TPAMI", "abstract", _population())

    def test_median_value_lands_mid_distribution(self):
        assert 40 <= self.ref.percentile("citation_density", 2.0) <= 60

    def test_extremes_saturate_without_overrunning(self):
        assert self.ref.percentile("citation_density", -99.0) == 0.0
        assert self.ref.percentile("citation_density", 99.0) == 100.0

    def test_percentile_is_monotonic(self):
        vals = [0.5, 1.5, 2.0, 2.5, 3.5]
        pcts = [self.ref.percentile("citation_density", v) for v in vals]
        assert pcts == sorted(pcts)

    def test_unknown_feature_raises(self):
        with pytest.raises(KeyError):
            self.ref.percentile("not_a_feature", 1.0)


class TestInformative:
    def test_constant_feature_is_not_informative(self):
        ref = Reference.fit("TPAMI", "abstract", _population())
        # Nothing in the population sets equation_ref_density; it is all zeros.
        assert not ref.is_informative("equation_ref_density")
        assert ref.is_informative("citation_density")

    def test_constant_features_never_produce_findings(self):
        ref = Reference.fit("TPAMI", "abstract", _population())
        out = score_section(ref, _vec(citation_density=2.0, n_words=200,
                                      equation_ref_density=9.9))
        assert [f.feature for f in out["findings"]] == []


class TestScoreSection:
    def setup_method(self):
        self.ref = Reference.fit("TPAMI", "abstract", _population())

    def test_typical_draft_has_no_findings(self):
        out = score_section(self.ref, _vec(citation_density=2.0, n_words=200))
        assert out["findings"] == []

    def test_thin_citations_flagged_below(self):
        out = score_section(self.ref, _vec(citation_density=0.05, n_words=200))
        found = {f.feature: f for f in out["findings"]}
        assert "citation_density" in found
        assert found["citation_density"].direction == "below"
        assert found["citation_density"].venue_median == pytest.approx(2.0, abs=0.15)

    def test_excess_flagged_above(self):
        out = score_section(self.ref, _vec(citation_density=9.0, n_words=200))
        found = {f.feature: f for f in out["findings"]}
        assert found["citation_density"].direction == "above"

    def test_findings_ordered_most_extreme_first(self):
        out = score_section(self.ref, _vec(citation_density=0.01, n_words=195))
        pcts = [min(f.percentile, 100 - f.percentile) for f in out["findings"]]
        assert pcts == sorted(pcts)

    def test_reports_reference_size(self):
        out = score_section(self.ref, _vec(citation_density=2.0, n_words=200))
        assert out["n_reference_papers"] == 500


class TestFitCorpus:
    def test_large_venue_gets_own_reference(self):
        rs = fit_corpus({"TPAMI": {"abstract": _population(400)}})
        ref = rs.get("TPAMI", "abstract")
        assert ref is not None and ref.venue == "TPAMI"

    def test_thin_venue_pools_into_tier(self):
        rs = fit_corpus(
            {"JACM": {"abstract": _population(150, seed=1)},
             "VLDBJ": {"abstract": _population(200, seed=2)}},
            venue_tier={"JACM": "tier:q1", "VLDBJ": "tier:q1"},
            min_support=300,
        )
        # Neither venue clears min_support alone, but pooled they do.
        ref = rs.get("JACM", "abstract")
        assert ref is not None
        assert ref.venue == "tier:q1"
        assert ref.n_papers == 350
        assert sorted(ref.pooled_from) == ["JACM", "VLDBJ"]
        # Both thin venues resolve to the same pooled reference.
        assert rs.get("VLDBJ", "abstract") is ref

    def test_pooled_tier_still_below_support_is_dropped(self):
        rs = fit_corpus(
            {"JACM": {"abstract": _population(50, seed=1)},
             "VLDBJ": {"abstract": _population(60, seed=2)}},
            venue_tier={"JACM": "tier:q1", "VLDBJ": "tier:q1"},
            min_support=300,
        )
        # Pooling 110 papers does not make a p10 estimate trustworthy.
        assert rs.get("JACM", "abstract") is None

    def test_thin_venue_without_tier_is_dropped(self):
        rs = fit_corpus({"JACM": {"abstract": _population(50)}}, min_support=400)
        assert rs.get("JACM", "abstract") is None

    def test_roundtrip_through_disk(self, tmp_path):
        rs = fit_corpus({"TPAMI": {"abstract": _population(400)}})
        path = tmp_path / "refs.json"
        rs.save(path)
        back = ReferenceSet.load(path)
        assert back.venues() == ["TPAMI"]
        a = rs.get("TPAMI", "abstract").percentile("citation_density", 2.0)
        b = back.get("TPAMI", "abstract").percentile("citation_density", 2.0)
        assert a == b
