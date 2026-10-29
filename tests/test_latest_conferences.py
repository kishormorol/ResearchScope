"""Tests for keeping the newest A* conference editions in ResearchScope — offline.

Covers the virtual-site connector's record mapping, which archived conference
blocks count as settled, and the cap reserve for just-published editions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.connectors.miniconf_connector import MiniconfConnector, _clean_abstract, _parse_tier
from src.normalization.schema import Paper
from src.pipeline import _settled_conf_keys
from src.sitegen.generator import SiteGenerator

THIS_YEAR = datetime.now(timezone.utc).year


def _rec(name: str, *, eventtype: str = "Poster", decision: str = "Accept (poster)",
         page: str = "/virtual/2026/poster/1", uid: str = "u1") -> dict:
    """A record shaped like neurips.cc/static/virtual/data/*-orals-posters.json."""
    return {
        "name": name, "uid": uid, "eventtype": eventtype, "decision": decision,
        "virtualsite_url": page,
        "paper_url": "https://openreview.net/forum?id=abc",
        "authors": [{"id": 1, "fullname": "Ada Lovelace"}, {"id": 2, "fullname": "Alan Turing"}],
    }


def _papers(records: list[dict]) -> list[Paper]:
    return MiniconfConnector.records_to_papers(records, "https://neurips.cc", "NeurIPS", "A*", 2026)


# ── miniconf connector ────────────────────────────────────────────────────────

def test_record_maps_to_conference_paper():
    [p] = _papers([_rec("Sparse Attention Is Enough")])
    assert p.venue == "NeurIPS" and p.year == 2026 and p.conference_rank == "A*"
    assert p.source_type == "conference"
    assert p.authors == ["Ada Lovelace", "Alan Turing"]
    assert p.paper_url == "https://neurips.cc/virtual/2026/poster/1"
    assert p.pdf_url == "https://openreview.net/pdf?id=abc"
    assert p.presentation_type == "poster"


def test_repeated_sessions_collapse_to_one_paper_with_strongest_tier():
    records = [
        _rec("Sparse Attention Is Enough", eventtype="Oral", decision="Accept (oral)",
             page="/virtual/2026/oral/2"),
        _rec("Sparse Attention Is Enough", decision="Accept (oral)", page="/virtual/2026/poster/3"),
        _rec("Sparse  attention is enough!", decision="Accept (oral)", page="/virtual/2026/poster/4"),
    ]
    [p] = _papers(records)
    assert p.presentation_type == "oral"
    assert "/poster/" in p.paper_url  # the poster page is the one with the abstract


def test_rejected_and_untitled_records_are_dropped():
    records = [_rec("Kept"), _rec("Withdrawn", decision="Reject"), _rec("")]
    assert [p.title for p in _papers(records)] == ["Kept"]


def test_missing_decision_still_counts_as_accepted_poster():
    [p] = _papers([_rec("Session Duplicate", decision=None)])
    assert p.presentation_type == "poster"


def test_parse_tier_and_clean_abstract():
    assert _parse_tier("Accept (Spotlight)", "Poster") == "spotlight"
    assert _parse_tier("", "Oral") == "oral"
    assert _clean_abstract("<p>Abstract</p>\n  We <b>show</b> &amp; prove.") == "We show & prove."


# ── settled conference blocks ─────────────────────────────────────────────────

def _conf(venue: str, year: int, n: int) -> list[Paper]:
    return [Paper(id=f"{venue}{year}-{i}", title=f"t{i}", venue=venue, year=year,
                  source_type="conference") for i in range(n)]


def test_partial_past_block_is_not_settled(monkeypatch):
    monkeypatch.delenv("CONF_REFRESH_YEARS", raising=False)
    papers = _conf("NeurIPS", 2024, 300) + _conf("CVPR", 2024, 29)
    assert _settled_conf_keys(papers) == {"NeurIPS:2024"}


def test_current_year_is_never_settled(monkeypatch):
    monkeypatch.delenv("CONF_REFRESH_YEARS", raising=False)
    assert _settled_conf_keys(_conf("ICML", THIS_YEAR, 3000)) == set()


def test_refresh_years_forces_refetch(monkeypatch):
    monkeypatch.setenv("CONF_REFRESH_YEARS", "2024, 2023")
    papers = _conf("NeurIPS", 2024, 300) + _conf("ICML", 2023, 300) + _conf("ICLR", 2022, 300)
    assert _settled_conf_keys(papers) == {"ICLR:2022"}


# ── latest-edition reserve in the site caps ───────────────────────────────────

def _scored(venue: str, year: int, n: int, score: float, rank: str = "A*") -> list[Paper]:
    return [Paper(id=f"{venue}{year}-{i}", title=f"{venue} {year} {i}", venue=venue, year=year,
                  conference_rank=rank, source_type="conference", paper_score=score)
            for i in range(n)]


def _by_score(papers: list[Paper]) -> list[Paper]:
    return sorted(papers, key=lambda p: -p.paper_score)


def test_new_editions_get_reserved_slots(monkeypatch):
    monkeypatch.setattr(SiteGenerator, "LATEST_EDITION_SHARE", 0.4)
    old = _scored("NeurIPS", THIS_YEAR - 3, 100, 9.0)   # well-cited, would fill the cap
    new = _scored("NeurIPS", THIS_YEAR, 50, 5.0)
    kept = SiteGenerator._with_latest_editions(_by_score(old + new), 100)
    assert len(kept) == 100
    assert sum(p.year == THIS_YEAR for p in kept) == 40
    assert [p.paper_score for p in kept] == sorted((p.paper_score for p in kept), reverse=True)


def test_reserve_is_shared_across_venues(monkeypatch):
    monkeypatch.setattr(SiteGenerator, "LATEST_EDITION_SHARE", 0.5)
    filler = _scored("ICLR", THIS_YEAR - 4, 100, 9.0)
    big = _scored("NeurIPS", THIS_YEAR, 80, 6.0)
    small = _scored("COLM", THIS_YEAR, 10, 4.0)
    kept = SiteGenerator._with_latest_editions(_by_score(filler + big + small), 40)
    assert sum(p.venue == "COLM" for p in kept) == 10
    assert sum(p.venue == "NeurIPS" for p in kept) == 10


def test_stale_and_non_astar_editions_get_no_reserve(monkeypatch):
    monkeypatch.setattr(SiteGenerator, "LATEST_EDITION_SHARE", 0.5)
    filler = _scored("ICLR", THIS_YEAR - 4, 100, 9.0)
    stale = _scored("ECCV", THIS_YEAR - 2, 20, 3.0)          # its newest year is too old
    rank_a = _scored("AISTATS", THIS_YEAR, 20, 3.0, rank="A")
    kept = SiteGenerator._with_latest_editions(_by_score(filler + stale + rank_a), 40)
    assert all(p.venue == "ICLR" for p in kept)


def test_under_cap_returns_everything():
    papers = _scored("ICML", THIS_YEAR, 5, 5.0)
    assert SiteGenerator._with_latest_editions(papers, 10) == papers


# ── PMLR listing parser and S2 bulk fields ────────────────────────────────────

_PMLR_CURRENT = """
<div class="paper">
  <p class="title">TUR-DPO: Topology-Aware Preference Optimization</p>
  <p class="details">
    <span class="authors">Abdulhady Abas,&nbsp;Fatemeh Daneshfar</span>;
    <span class="info"><i>Proceedings of ICML</i>, PMLR 306:1-21</span>
  </p>
  <p class="links">
    [<a href="https://proceedings.mlr.press/v306/abas26a.html">abs</a>][<a href="https://example.org/abas26a.pdf">Download PDF</a>][<a href="https://openreview.net/forum?id=Y">OpenReview</a>]</p>
</div>"""

_PMLR_LEGACY = """
<div class="paper">
  <p class="title"><a href="/v119/abbas20a.html">Old Layout Paper</a></p>
  <p class="authors">Zaheer Abbas, Samuel Sokota</p>
</div>"""


def _parse(html: str) -> list[dict]:
    from src.connectors.pmlr_connector import _PMLRParser
    parser = _PMLRParser()
    parser.feed(html)
    return parser.papers


def test_pmlr_parser_reads_current_layout():
    [rec] = _parse(_PMLR_CURRENT)
    assert rec["title"] == "TUR-DPO: Topology-Aware Preference Optimization"
    assert rec["authors"] == ["Abdulhady Abas", "Fatemeh Daneshfar"]
    assert rec["url"] == "https://proceedings.mlr.press/v306/abas26a.html"
    assert rec["pdf_url"] == "https://example.org/abas26a.pdf"


def test_pmlr_parser_still_reads_legacy_layout():
    [rec] = _parse(_PMLR_LEGACY)
    assert rec["url"] == "https://proceedings.mlr.press/v119/abbas20a.html"
    assert rec["authors"] == ["Zaheer Abbas", "Samuel Sokota"]


def test_s2_bulk_fields_exclude_affiliations():
    from src.connectors.semantic_scholar_connector import _BULK_FIELDS
    assert "authors.affiliations" not in _BULK_FIELDS
    assert "abstract" in _BULK_FIELDS and "authors.name" in _BULK_FIELDS
