"""Paper ranking / read-next prioritization."""

from __future__ import annotations

from researchscope.models.paper import Paper


def rank_papers(
    papers: list[Paper],
    weights: dict[str, float] | None = None,
) -> list[Paper]:
    """Return *papers* sorted by a configurable relevance score (descending).

    The default scoring formula combines:

    * **citation_count** – raw citation popularity (weight ``"citations"``).
    * **recency** – papers published more recently receive a higher score
      (weight ``"recency"``).

    Args:
        papers: Unordered list of papers to rank.
        weights: Optional mapping of weight names to float multipliers.
            Accepted keys: ``"citations"``, ``"recency"``.
            Defaults to ``{"citations": 1.0, "recency": 0.5}``.

    Returns:
        A new list of papers sorted from highest to lowest relevance score.
    """
    if weights is None:
        weights = {"citations": 1.0, "recency": 0.5}

    citation_w = weights.get("citations", 1.0)
    recency_w = weights.get("recency", 0.5)

    from datetime import date

    today = date.today()

    def _score(paper: Paper) -> float:
        score = citation_w * paper.citation_count
        if paper.published is not None:
            age_days = max((today - paper.published).days, 0)
            # Decay: score decreases by 1 per 30 days of age
            score += recency_w * max(0.0, 365 - age_days / 30)
        return score

    return sorted(papers, key=_score, reverse=True)
