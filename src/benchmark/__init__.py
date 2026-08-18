"""
Section-level writing benchmark for ResearchScope.

Scores a draft paper's sections against reference distributions fitted over
published papers at a *target venue*, and reports where the draft falls
outside the norm. The unit of analysis is the (paper, section) pair over the
seven canonical sections defined in `src.fulltext`.

The benchmark is deliberately a *conformance* model, not an accept/reject
classifier: the corpus contains only accepted papers, so there is no negative
class to learn from. What it can say is "your Related Work cites far fewer
works than is typical for this venue" — which is actionable — rather than
"this will be rejected", which the data cannot support.

Feature tiers:
    T1  surface / structural   — features.py, needs only section text
    T2  rhetorical moves       — sentence-level discourse structure (planned)
    T3  semantic typicality    — embedding density per venue (planned)

Venues with too few papers to support their own reference distribution are
pooled into a tier-level reference instead; see reference.py.
"""
from __future__ import annotations

# Minimum papers required before a venue gets its own reference distribution.
# Below this the venue is pooled into its tier. Chosen so that a p10/p90 read
# off the empirical distribution rests on at least ~20 papers per tail.
MIN_VENUE_SUPPORT = 200
