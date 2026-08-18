"""
Per-(venue, section) reference distributions and conformance scoring.

A reference is the empirical distribution of each T1 feature over published
papers at one venue, for one canonical section. Scoring a draft section means
locating each of its features in that distribution and reporting the
percentile, plus a flag when the value sits outside the central band.

Distributions are stored as a 101-point quantile grid rather than the raw
values: it is ~3 orders of magnitude smaller than keeping every paper's
vector, is enough to recover any percentile to within one point, and makes
the fitted benchmark a small artifact that can ship with the paper.

Venues with fewer than MIN_VENUE_SUPPORT papers do not get their own
reference — fitting a p10 on 40 papers estimates the tail from four of them.
Those venues fall back to a pooled tier reference; see `fit_corpus`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.benchmark import MIN_VENUE_SUPPORT
from src.benchmark.features import FEATURE_NAMES

# Percentile band treated as "typical". Outside it we surface a finding.
LOW_PCT = 10.0
HIGH_PCT = 90.0

_GRID = np.arange(0, 101, 1)


@dataclass
class Reference:
    """Quantile grids for one (venue, section)."""

    venue: str
    section: str
    n_papers: int
    # feature -> 101 values, the 0th..100th percentile
    quantiles: dict[str, list[float]] = field(default_factory=dict)
    pooled_from: list[str] = field(default_factory=list)

    @classmethod
    def fit(cls, venue: str, section: str,
            vectors: list[dict[str, float]],
            pooled_from: list[str] | None = None) -> "Reference":
        quantiles: dict[str, list[float]] = {}
        for name in FEATURE_NAMES:
            values = np.array([v.get(name, 0.0) for v in vectors], dtype=float)
            quantiles[name] = np.percentile(values, _GRID).round(6).tolist()
        return cls(venue=venue, section=section, n_papers=len(vectors),
                   quantiles=quantiles, pooled_from=pooled_from or [])

    def percentile(self, feature: str, value: float) -> float:
        """Where `value` falls in this reference, as a 0-100 percentile.

        Ties are resolved to the midpoint of the tied block. That matters for
        features that are zero for most papers (equation references in an
        abstract, say): a draft that is also zero should read as typical,
        not as sitting at the top of the distribution.
        """
        grid = self.quantiles.get(feature)
        if not grid:
            raise KeyError(f"no reference for feature {feature!r}")
        arr = np.asarray(grid)
        lo = float(np.searchsorted(arr, value, side="left"))
        hi = float(np.searchsorted(arr, value, side="right"))
        return max(0.0, min(100.0, (lo + hi) / 2.0))

    def is_informative(self, feature: str) -> bool:
        """False when every reference paper shares one value for this feature.

        Such a feature has no spread to compare a draft against, so reporting
        a departure from it would be noise.
        """
        grid = self.quantiles[feature]
        return grid[0] != grid[-1]

    def band(self, feature: str) -> tuple[float, float]:
        grid = self.quantiles[feature]
        return grid[int(LOW_PCT)], grid[int(HIGH_PCT)]

    def to_dict(self) -> dict:
        return {
            "venue": self.venue, "section": self.section,
            "n_papers": self.n_papers, "quantiles": self.quantiles,
            "pooled_from": self.pooled_from,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Reference":
        return cls(venue=d["venue"], section=d["section"],
                   n_papers=d["n_papers"], quantiles=d["quantiles"],
                   pooled_from=d.get("pooled_from", []))


@dataclass
class Finding:
    """One way a draft section departs from the venue norm."""

    feature: str
    value: float
    percentile: float
    direction: str          # "below" | "above"
    venue_low: float
    venue_high: float
    venue_median: float


def score_section(ref: Reference, vector: dict[str, float]) -> dict:
    """Locate every feature of `vector` in `ref`; flag out-of-band ones."""
    percentiles: dict[str, float] = {}
    findings: list[Finding] = []
    for name in FEATURE_NAMES:
        value = float(vector.get(name, 0.0))
        pct = ref.percentile(name, value)
        percentiles[name] = pct
        if ref.is_informative(name) and (pct < LOW_PCT or pct > HIGH_PCT):
            low, high = ref.band(name)
            findings.append(Finding(
                feature=name, value=value, percentile=pct,
                direction="below" if pct < LOW_PCT else "above",
                venue_low=low, venue_high=high,
                venue_median=ref.quantiles[name][50],
            ))
    # Most extreme departures first — that is the order an author should read.
    findings.sort(key=lambda f: min(f.percentile, 100.0 - f.percentile))
    return {
        "venue": ref.venue,
        "section": ref.section,
        "n_reference_papers": ref.n_papers,
        "percentiles": percentiles,
        "findings": findings,
    }


class ReferenceSet:
    """All fitted references, keyed by (venue, section), with tier fallback."""

    def __init__(self, references: dict[tuple[str, str], Reference],
                 venue_tier: dict[str, str] | None = None):
        self._refs = references
        self._venue_tier = venue_tier or {}

    def get(self, venue: str, section: str) -> Reference | None:
        ref = self._refs.get((venue, section))
        if ref is not None:
            return ref
        tier = self._venue_tier.get(venue)
        if tier:
            return self._refs.get((tier, section))
        return None

    def venues(self) -> list[str]:
        return sorted({v for v, _ in self._refs})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "venue_tier": self._venue_tier,
            "references": [r.to_dict() for r in self._refs.values()],
        }
        path.write_text(json.dumps(payload))

    @classmethod
    def load(cls, path: Path) -> "ReferenceSet":
        payload = json.loads(path.read_text())
        refs = {}
        for d in payload["references"]:
            r = Reference.from_dict(d)
            refs[(r.venue, r.section)] = r
        return cls(refs, payload.get("venue_tier", {}))


def fit_corpus(sections_by_venue: dict[str, dict[str, list[dict[str, float]]]],
               venue_tier: dict[str, str] | None = None,
               min_support: int = MIN_VENUE_SUPPORT) -> ReferenceSet:
    """Fit references from {venue: {section: [feature_vector, ...]}}.

    Venues below `min_support` for a section contribute their vectors to their
    tier's pooled reference instead of getting one of their own.
    """
    venue_tier = venue_tier or {}
    refs: dict[tuple[str, str], Reference] = {}
    pooled: dict[tuple[str, str], list[dict[str, float]]] = {}
    pooled_sources: dict[tuple[str, str], list[str]] = {}

    for venue, by_section in sections_by_venue.items():
        for section, vectors in by_section.items():
            if len(vectors) >= min_support:
                refs[(venue, section)] = Reference.fit(venue, section, vectors)
            else:
                tier = venue_tier.get(venue)
                if not tier:
                    continue
                pooled.setdefault((tier, section), []).extend(vectors)
                pooled_sources.setdefault((tier, section), []).append(venue)

    for (tier, section), vectors in pooled.items():
        if len(vectors) >= min_support:
            refs[(tier, section)] = Reference.fit(
                tier, section, vectors, sorted(pooled_sources[(tier, section)])
            )
    return ReferenceSet(refs, venue_tier)
