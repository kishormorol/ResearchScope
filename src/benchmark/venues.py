"""Venue metadata: field, quartile rank, and the tier a thin venue pools into.

Sourced from the journal recommender ResearchScope already publishes, so the
benchmark and the recommender agree on what a venue *is* rather than drifting
apart with two hand-maintained lists.

Tiers are keyed on (field, rank) rather than rank alone. Pooling TPAMI into a
generic "Q1" bucket alongside Nature Communications would mix computer-vision
and multidisciplinary-science writing norms, which are exactly the norms the
benchmark exists to keep apart.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_RECOMMENDER = Path("site/data/journal_recommender.json")

# The recommender's `field` labels are tuned for venue *suggestion*, and a few
# are wrong in ways that would corrupt tier pooling here. Overridden with the
# reason, rather than editing the recommender, which serves a different product.
_FIELD_OVERRIDES = {
    # Multidisciplinary science, not ML. It is ~58% of the journal corpus, so
    # letting it pool into tier:ML:Q1 would drown the CS venues it pools with.
    "NatComms": "MULTI",
    # Theory of computing; the NLP label is simply a mislabel.
    "JACM": "THEORY",
    # Speech and language processing sits with the NLP journals, not generic ML.
    "TASLP": "NLP",
}


@lru_cache(maxsize=1)
def venue_meta(path: Path | None = None) -> dict[str, dict]:
    """{venue_short: {field, rank, name}} for every known journal venue."""
    src = path or _RECOMMENDER
    payload = json.loads(src.read_text())
    return {
        v["short"]: {
            "field": _FIELD_OVERRIDES.get(v["short"], v.get("field", "?")),
            "rank": v.get("rank", "?"),
            "name": v.get("name", v["short"]),
        }
        for v in payload.get("venues", [])
    }


def tier_of(venue: str) -> str | None:
    """Pooling key for a venue, e.g. 'tier:CV:Q1'. None if venue is unknown."""
    meta = venue_meta().get(venue)
    if not meta:
        return None
    return f"tier:{meta['field']}:{meta['rank']}"


def venue_tier_map() -> dict[str, str]:
    return {v: f"tier:{m['field']}:{m['rank']}" for v, m in venue_meta().items()}
