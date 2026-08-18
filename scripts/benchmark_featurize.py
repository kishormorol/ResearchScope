"""Featurise a corpus snapshot once and cache the matrix to .npz.

    python scripts/benchmark_featurize.py --section abstract

Extracting T1 features over 76k papers takes minutes; every downstream
experiment (reference fitting, venue discrimination, revision deltas) needs
the same matrix, so it is computed once and cached.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.features import FEATURE_NAMES, extract_features

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_MIN_CHARS = 200


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="data/benchmark/journals.jsonl")
    ap.add_argument("--section", default="abstract")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = Path(args.out or f"data/benchmark/features_{args.section}.npz")
    X, venues, ids, years = [], [], [], []
    with Path(args.snapshot).open() as fh:
        for n, line in enumerate(fh, 1):
            row = json.loads(line)
            text = (row.get(args.section) or "").strip()
            if not row.get("venue") or len(text) < _MIN_CHARS:
                continue
            f = extract_features(text)
            X.append([f[k] for k in FEATURE_NAMES])
            venues.append(row["venue"])
            ids.append(row["id"])
            years.append(row.get("year") or 0)
            if n % 10000 == 0:
                log.info("  %d papers scanned, %d featurised", n, len(X))

    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out,
        X=np.asarray(X, dtype=np.float32),
        venue=np.asarray(venues),
        paper_id=np.asarray(ids),
        year=np.asarray(years, dtype=np.int32),
        feature_names=np.asarray(FEATURE_NAMES),
    )
    log.info("wrote %s: %d x %d", out, len(X), len(FEATURE_NAMES))


if __name__ == "__main__":
    main()
