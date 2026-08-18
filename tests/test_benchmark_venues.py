"""Venue metadata and tier pooling keys."""
from __future__ import annotations

from src.benchmark.venues import tier_of, venue_meta, venue_tier_map


class TestVenueMeta:
    def test_known_venues_present(self):
        meta = venue_meta()
        for v in ("TPAMI", "NatComms", "TACL", "IJCV"):
            assert v in meta
            assert meta[v]["rank"] in {"Q1", "Q2"}

    def test_unknown_venue_absent(self):
        assert "NOT_A_VENUE" not in venue_meta()


class TestFieldOverrides:
    def test_natcomms_is_not_pooled_with_ml_journals(self):
        # It is ~58% of the corpus; pooling it into tier:ML:Q1 would swamp
        # the CS venues that rely on that tier.
        assert tier_of("NatComms") != tier_of("TPAMI")
        assert venue_meta()["NatComms"]["field"] == "MULTI"

    def test_jacm_mislabel_corrected(self):
        assert venue_meta()["JACM"]["field"] == "THEORY"
        assert tier_of("JACM") != tier_of("TACL")

    def test_taslp_groups_with_nlp(self):
        assert tier_of("TASLP") == tier_of("TACL")


class TestTierOf:
    def test_shape(self):
        assert tier_of("TPAMI") == "tier:ML:Q1"

    def test_unknown_venue_has_no_tier(self):
        assert tier_of("NOT_A_VENUE") is None

    def test_same_field_and_rank_share_a_tier(self):
        assert tier_of("IJCV") == tier_of("TIP") == "tier:CV:Q1"

    def test_rank_separates_tiers(self):
        assert tier_of("PR") != tier_of("IJCV")   # Q2 vs Q1, both CV

    def test_map_covers_every_known_venue(self):
        assert set(venue_tier_map()) == set(venue_meta())
