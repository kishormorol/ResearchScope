"""Snapshot the published corpus the benchmark is fitted against.

    python scripts/benchmark_snapshot.py --source journals
    python scripts/benchmark_snapshot.py --source conferences --max-pages 50

Writes JSONL to data/benchmark/<source>.jsonl. Safe to re-run: an interrupted
pull resumes from the last complete page.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.corpus import snapshot, total_papers

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="journals",
                    choices=["journals", "conferences"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    out = Path(args.out or f"data/benchmark/{args.source}.jsonl")
    if args.fresh and out.exists():
        out.unlink()

    total = total_papers(args.source)
    logging.info("corpus %s: %d papers -> %s", args.source, total, out)
    n = snapshot(out, args.source, args.max_pages, resume=not args.fresh)
    logging.info("done: %d rows in %s", n, out)


if __name__ == "__main__":
    main()
