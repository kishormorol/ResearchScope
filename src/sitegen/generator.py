"""
Static site data generator.

Writes JSON files into output_dir/ that the frontend consumes.
Also copies them into site/data/ so they are published on GitHub Pages.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.normalization.schema import Author, Lab, Paper, ResearchGap, Topic, University
from src import storage

log = logging.getLogger(__name__)


class SiteGenerator:
    """Write all JSON data files for the static frontend."""

    SITE_DATA_DIR = Path(__file__).parent.parent.parent / "site" / "data"

    # Venues treated as arXiv / unclassified (not conference proceedings)
    _ARXIV_VENUES = {"arXiv", "Unknown", "", None}

    # ── Frontend slice sizes — 1 000 per section × 3 sections = 3 000 total ──
    # Section 1: arXiv preprints  (papers.json)
    MAX_FRONTEND_ARXIV = 1_000
    # Section 2: A* conference papers only  (conferences.json)
    MAX_FRONTEND_CONF  = 1_000
    # Section 3: Q1 journal papers  (journals.json)
    MAX_FRONTEND_JOURNAL = 1_000

    # ── GitHub hard limit: 100 MB per file ────────────────────────────────────
    MAX_DB_PAPERS             = 7_500
    MAX_CONF_DB_PAPERS        = 20_000
    MAX_JOURNAL_DB_PAPERS     = 5_000
    # authors.json — slim, no paper_ids; ~0.4 KB/author
    #   5,000 × 0.4 KB = 2 MB  ✓ safe
    MAX_AUTHORS = 5_000
    # Share of each conference cap kept for the newest edition of every A*
    # conference. paper_score leans on citations and abstracts, so without a
    # reserve a just-published NeurIPS or CVPR is crowded out by older years.
    LATEST_EDITION_SHARE = 0.4
    # Topics/gaps caps — prevents raw tag explosion from bloating these lists
    MAX_TOPICS  = 150
    MAX_GAPS    = 100

    def generate(
        self,
        papers: list[Paper],
        authors: list[Author],
        topics: list[Topic],
        gaps: list[ResearchGap],
        output_dir: str = "data",
        labs: list[Lab] | None = None,
        universities: list[University] | None = None,
        editorial: dict | None = None,
    ) -> None:
        os.makedirs(output_dir, exist_ok=True)

        # Papers already sorted by paper_score descending from the pipeline.
        # Split into three independent pools.
        arxiv_papers   = [p for p in papers if p.source_type == "preprint" or p.venue in self._ARXIV_VENUES]
        journal_papers = [p for p in papers if p.source_type == "journal"]
        conf_papers    = [p for p in papers if p.source_type == "conference" and p.venue not in self._ARXIV_VENUES]
        # Section 2 is A* only — the most impactful conference research
        a_star_papers  = [p for p in conf_papers if p.conference_rank == "A*"]

        # ── Persistent stores (committed to git, used by next pipeline run) ──────
        self._write(output_dir, "papers_db.json",
                    [p.to_dict() for p in arxiv_papers[: self.MAX_DB_PAPERS]])
        conf_db = self._with_latest_editions(conf_papers, self.MAX_CONF_DB_PAPERS)
        self._write(output_dir, "conferences_db.json",
                    [self._slim(p) for p in conf_db])
        self._write(output_dir, "journals_db.json",
                    [self._slim(p) for p in journal_papers[: self.MAX_JOURNAL_DB_PAPERS]])

        # ── Section 1: arXiv preprints — top 1 000 by paper_score ───────────────
        self._write(output_dir, "papers.json",
                    [self._slim(p) for p in arxiv_papers[: self.MAX_FRONTEND_ARXIV]])

        # ── Section 2: A* conference papers — top 1 000 by paper_score ──────────
        self._write(output_dir, "conferences.json",
                    [self._slim(p) for p in
                     self._with_latest_editions(a_star_papers, self.MAX_FRONTEND_CONF)])

        # ── Section 3: Q1 journal papers — top 1 000 by paper_score ─────────────
        self._write(output_dir, "journals.json",
                    [self._slim(p) for p in journal_papers[: self.MAX_FRONTEND_JOURNAL]])

        # ── Search index — arXiv DB + top conference papers ─────────────────────
        # _search_entry is ultra-light (~250 B/paper) so 20 K entries ≈ 5 MB — safe.
        all_db = arxiv_papers[: self.MAX_DB_PAPERS] + conf_db
        self._write(output_dir, "search_index.json",
                    [self._search_entry(p) for p in all_db])

        # Cap + slim authors — full paper_ids list bloats fast with conference data.
        # Sort by momentum_score desc; top MAX_AUTHORS only, paper_ids stripped.
        top_authors = sorted(authors, key=lambda a: (-a.momentum_score, -a.avg_paper_score))
        self._write(output_dir, "authors.json",
                    [self._slim_author(a) for a in top_authors[: self.MAX_AUTHORS]])
        # Cap topics and gaps — raw OpenReview keywords can explode these counts
        top_topics = sorted(topics, key=lambda t: (-t.trend_score, -len(t.paper_ids)))
        self._write(output_dir, "topics.json",      [t.to_dict() for t in top_topics[: self.MAX_TOPICS]])
        top_gaps = sorted(gaps, key=lambda g: (-g.frequency, -g.confidence))
        self._write(output_dir, "gaps.json",        [g.to_dict() for g in top_gaps[: self.MAX_GAPS]])
        self._write(output_dir, "labs.json",        [l.to_dict() for l in (labs or [])])
        self._write(output_dir, "universities.json",[u.to_dict() for u in (universities or [])])
        self._write(output_dir, "editorial.json",   editorial or {})
        self._write(output_dir, "stats.json",       self._stats(papers, authors, topics, gaps, labs or [], universities or []))

        # Mirror into site/data/ so Pages always has the latest data
        self._mirror_to_site(output_dir)

        paper_dicts = [p.to_dict() for p in papers]

        # Sync to Railway PostgreSQL (used by FastAPI backend)
        from src.storage import railway_store
        railway_store.sync(papers=paper_dicts)

        # Push to Hugging Face Hub dataset (for LLM training) — non-fatal
        try:
            from src.storage import hf_dataset
            hf_dataset.push(papers=paper_dicts)
        except Exception as exc:
            log.warning("HF dataset push failed (non-fatal): %s", exc)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @classmethod
    def _with_latest_editions(cls, papers: list[Paper], cap: int) -> list[Paper]:
        """Top ``cap`` papers by score, with part of the cap kept for new editions.

        Up to ``LATEST_EDITION_SHARE`` of the slots go to the newest edition of
        each A* conference (its latest year, if that is this year or last),
        shared round-robin across venues in score order so one big conference
        cannot take them all. The rest are filled by score as before. ``papers``
        must already be sorted by paper_score; the result keeps that order.
        """
        if len(papers) <= cap:
            return list(papers)
        min_year = datetime.now(timezone.utc).year - 1
        newest: dict[str, int] = {}
        for p in papers:
            if p.conference_rank == "A*" and p.year:
                newest[p.venue] = max(newest.get(p.venue, 0), int(p.year))
        queues: dict[str, list[Paper]] = {}
        for p in papers:
            year = int(p.year or 0)
            if p.conference_rank == "A*" and year >= min_year and year == newest.get(p.venue):
                queues.setdefault(p.venue, []).append(p)

        reserved: list[Paper] = []
        budget = int(cap * cls.LATEST_EDITION_SHARE)
        depth = 0
        while len(reserved) < budget and any(depth < len(q) for q in queues.values()):
            for q in queues.values():
                if depth < len(q) and len(reserved) < budget:
                    reserved.append(q[depth])
            depth += 1

        keep = {id(p) for p in reserved}
        for p in papers:
            if len(keep) >= cap:
                break
            keep.add(id(p))
        return [p for p in papers if id(p) in keep]

    # Creator-content and internal fields never needed by the browser UI
    _STRIP_FIELDS = {
        "tweet_thread", "linkedin_post", "newsletter_blurb", "video_script_outline",
        "plain_english_explanation", "technical_summary", "score_breakdown",
        "research_gap_signals", "limitations", "future_work",
        "canonical_id", "author_ids", "affiliations_raw", "lab_ids", "university_ids",
        "cluster_id", "prerequisites", "fetched_at",
    }

    @staticmethod
    def _slim_author(author: Author) -> dict:
        """Return a browser-friendly author dict — drops bulky paper_id lists."""
        d = author.to_dict()
        # paper_ids can be thousands of strings for prolific authors — drop it.
        # The frontend only needs the count and recent subset.
        d.pop("paper_ids", None)
        d.pop("momentum_breakdown", None)
        d.pop("summary_profile", None)
        d["paper_count"] = len(author.paper_ids)
        return d

    @classmethod
    def _slim(cls, paper: Paper) -> dict:
        """Return a browser-friendly dict — drops heavy fields not shown in the UI."""
        d = paper.to_dict()
        for f in cls._STRIP_FIELDS:
            d.pop(f, None)
        return d

    @staticmethod
    def _search_entry(paper: Paper) -> dict:
        """Ultra-light record for the client-side search index."""
        return {
            "id":          paper.id,
            "title":       paper.title,
            "abstract":    (paper.abstract or "")[:300],
            "authors":     paper.authors[:5],
            "venue":       paper.venue,
            "year":        paper.year,
            "paper_score": round(paper.paper_score, 1),
            "paper_url":   paper.paper_url,
            "tags":        paper.tags[:5],
        }

    _GITHUB_FILE_LIMIT = 100 * 1024 * 1024   # 100 MB hard limit

    @classmethod
    def _write(cls, directory: str, filename: str, data: object) -> None:
        import logging
        log = logging.getLogger(__name__)
        path = os.path.join(directory, filename)
        serialized = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        size = len(serialized.encode("utf-8"))
        mb = size / 1048576
        if size >= cls._GITHUB_FILE_LIMIT:
            raise RuntimeError(
                f"{filename} would be {mb:.1f} MB — exceeds GitHub's 100 MB limit. "
                "Reduce the cap constants in SiteGenerator."
            )
        if size >= cls._GITHUB_FILE_LIMIT * 0.85:
            log.warning("%s is %.1f MB — approaching GitHub's 100 MB limit!", filename, mb)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(serialized)

    # Files kept in the pipeline output dir but NOT served to the browser
    _DB_ONLY_FILES = {"papers_db.json", "conferences_db.json"}

    def _mirror_to_site(self, output_dir: str) -> None:
        site_data = self.SITE_DATA_DIR
        site_data.mkdir(parents=True, exist_ok=True)
        src = Path(output_dir)
        for json_file in src.glob("*.json"):
            shutil.copy2(json_file, site_data / json_file.name)

    @staticmethod
    def _stats(
        papers: list[Paper],
        authors: list[Author],
        topics: list[Topic],
        gaps: list[ResearchGap],
        labs: list[Lab],
        universities: list[University],
    ) -> dict:
        venues: dict[str, int] = {}
        sources: dict[str, int] = {}
        difficulty_dist: dict[str, int] = {}
        type_dist: dict[str, int] = {}
        year_dist: dict[int, int] = {}

        for p in papers:
            venues[p.venue] = venues.get(p.venue, 0) + 1
            sources[p.source] = sources.get(p.source, 0) + 1
            dl = p.difficulty_level or "L2"
            difficulty_dist[dl] = difficulty_dist.get(dl, 0) + 1
            pt = p.paper_type or "methods"
            type_dist[pt] = type_dist.get(pt, 0) + 1
            if p.year:
                year_dist[p.year] = year_dist.get(p.year, 0) + 1

        gap_type_dist: dict[str, int] = {}
        for g in gaps:
            gap_type_dist[g.gap_type] = gap_type_dist.get(g.gap_type, 0) + 1

        return {
            "total_papers":       len(papers),
            "total_authors":      len(authors),
            "total_topics":       len(topics),
            "total_gaps":         len(gaps),
            "total_labs":         len(labs),
            "total_universities": len(universities),
            "papers_by_venue":    venues,
            "papers_by_source":   sources,
            "difficulty_distribution": difficulty_dist,
            "paper_type_distribution": type_dist,
            "papers_by_year":     {str(k): v for k, v in sorted(year_dist.items())},
            "gaps_by_type":       gap_type_dist,
            "generated_at":       datetime.now(timezone.utc).isoformat(),
        }
