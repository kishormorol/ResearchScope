"""Validation tests for the static Conference Recommender data."""
from __future__ import annotations

import json
from pathlib import Path

from src.sitegen import conference_recommender


ROOT = Path(__file__).resolve().parents[1]
RECOMMENDER_INDEX = ROOT / "site" / "data" / "conference_recommender.json"


def test_conference_recommender_uses_standard_data_outputs():
    assert conference_recommender.DEFAULT_OUTPUT == RECOMMENDER_INDEX
    assert RECOMMENDER_INDEX.exists()


def test_conference_recommender_index_schema():
    data = json.loads(RECOMMENDER_INDEX.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert len(data["venues"]) >= 10
    assert {f["id"] for f in data["fields"]} >= {"any", "ML", "NLP", "CV"}

    required = {
        "id", "short", "name", "type", "field", "rank", "paper_count",
        "keywords", "weighted_keywords", "expectations", "deadline", "accepted_papers",
    }
    for venue in data["venues"]:
        assert required <= venue.keys()
        assert venue["type"] == "conference"
        assert venue["keywords"]
        assert venue["weighted_keywords"]
        assert all({"term", "weight"} <= item.keys() for item in venue["weighted_keywords"])
        assert all(0 < item["weight"] <= 1 for item in venue["weighted_keywords"])
        assert venue["keywords"][0] == venue["weighted_keywords"][0]["term"]
        assert venue["expectations"]
        assert isinstance(venue["accepted_papers"], list)


def test_conference_recommender_has_generated_venues_and_deadlines():
    data = json.loads(RECOMMENDER_INDEX.read_text(encoding="utf-8"))
    venues = {v["short"]: v for v in data["venues"]}
    for short in ["ICLR", "NeurIPS", "ACL", "CVPR"]:
        assert short in venues

    assert venues["ICLR"]["paper_count"] > 0
    assert venues["ICLR"]["deadline"]["paper_deadline"]
    assert venues["NeurIPS"]["keywords"]
    assert "TfidfVectorizer" in data["source"]["method"]
