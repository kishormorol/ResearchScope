"""Fit per-(venue, section) reference distributions from a corpus snapshot.

    python scripts/benchmark_fit.py --section abstract

Abstracts need no GROBID, so the abstract references can be fitted from the
snapshot alone. Body sections are fitted from the section extraction output
once that lands.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark import MIN_VENUE_SUPPORT
from src.benchmark.features import extract_features
from src.benchmark.reference import fit_corpus
from src.benchmark.venues import venue_tier_map

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_MIN_ABSTRACT_CHARS = 200


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default="data/benchmark/journals.jsonl")
    ap.add_argument("--section", default="abstract")
    ap.add_argument("--out", default=None)
    ap.add_argument("--min-support", type=int, default=MIN_VENUE_SUPPORT)
    args = ap.parse_args()

    snap = Path(args.snapshot)
    out = Path(args.out or f"data/benchmark/references_{args.section}.json")

    by_venue: dict[str, dict[str, list[dict[str, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    skipped = 0
    total = 0
    with snap.open() as fh:
        for line in fh:
            row = json.loads(line)
            total += 1
            text = (row.get(args.section) or "").strip()
            venue = row.get("venue")
            # Stub abstracts ("No abstract available") would drag every
            # length-derived percentile toward zero.
            if not venue or len(text) < _MIN_ABSTRACT_CHARS:
                skipped += 1
                continue
            by_venue[venue][args.section].append(extract_features(text))

    log.info("read %d papers; %d skipped (missing venue or <%d chars)",
             total, skipped, _MIN_ABSTRACT_CHARS)

    refs = fit_corpus(by_venue, venue_tier_map(), args.min_support)
    refs.save(out)

    log.info("\n%-18s %8s  %s", "reference", "n", "kind")
    for venue in refs.venues():
        ref = refs.get(venue, args.section)
        if ref is None:
            continue
        kind = ("pooled from " + ", ".join(ref.pooled_from)
                if ref.pooled_from else "own")
        log.info("%-18s %8d  %s", venue, ref.n_papers, kind)

    dropped = [v for v in by_venue if refs.get(v, args.section) is None]
    if dropped:
        log.info("\nno reference (too thin even pooled): %s",
                 ", ".join(sorted(dropped)))
    log.info("\nwrote %s", out)


if __name__ == "__main__":
    main()
