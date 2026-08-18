"""Feedback rendering: every feature phrased, direction respected."""
from __future__ import annotations

import pytest

from src.benchmark.features import FEATURE_NAMES
from src.benchmark.feedback import explain, explain_all
from src.benchmark.reference import Finding


def _finding(feature="citation_density", direction="below", pct=3.0) -> Finding:
    return Finding(feature=feature, value=0.2, percentile=pct,
                   direction=direction, venue_low=1.0, venue_high=4.0,
                   venue_median=2.5)


class TestExplain:
    def test_every_feature_has_phrasing(self):
        for name in FEATURE_NAMES:
            fb = explain(_finding(feature=name), "TPAMI", "related_work")
            assert fb is not None, f"{name} has no phrasing"
            assert fb.message

    def test_unknown_feature_returns_none(self):
        assert explain(_finding(feature="mystery"), "TPAMI", "abstract") is None

    def test_message_names_venue_and_section(self):
        fb = explain(_finding(), "TPAMI", "related_work")
        assert "TPAMI" in fb.message
        assert "related work section" in fb.message

    def test_direction_changes_the_message(self):
        below = explain(_finding(direction="below"), "TPAMI", "abstract")
        above = explain(_finding(direction="above", pct=97.0), "TPAMI", "abstract")
        assert below.message != above.message

    def test_carries_the_numbers_through(self):
        fb = explain(_finding(), "TPAMI", "abstract")
        assert fb.your_value == 0.2
        assert fb.venue_median == 2.5
        assert fb.venue_range == (1.0, 4.0)
        assert fb.percentile == 3.0

    def test_never_states_a_verdict(self):
        # The corpus has no rejected papers, so feedback must not claim one.
        banned = ("reject", "will be rejected", "bad paper", "poor quality",
                  "accept", "will be accepted")
        for name in FEATURE_NAMES:
            for direction in ("below", "above"):
                fb = explain(_finding(feature=name, direction=direction),
                             "TPAMI", "abstract")
                lowered = fb.message.lower()
                assert not any(b in lowered for b in banned), name

    def test_unknown_section_falls_back_to_raw_name(self):
        fb = explain(_finding(), "TPAMI", "appendix")
        assert "appendix" in fb.message


class TestExplainAll:
    def test_preserves_finding_order(self):
        scored = {
            "venue": "TPAMI", "section": "abstract",
            "findings": [_finding("citation_density", "below", 2.0),
                         _finding("hedge_density", "above", 95.0)],
        }
        out = explain_all(scored)
        assert [f.feature for f in out] == ["citation_density", "hedge_density"]

    def test_drops_unphrased_findings(self):
        scored = {"venue": "TPAMI", "section": "abstract",
                  "findings": [_finding("mystery"), _finding("hedge_density")]}
        assert [f.feature for f in explain_all(scored)] == ["hedge_density"]

    def test_empty_findings(self):
        assert explain_all({"venue": "TPAMI", "section": "abstract",
                            "findings": []}) == []
