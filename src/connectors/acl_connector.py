"""
ACL Anthology connector.

Two modes:
  fetch(query, max_results)   — keyword search via the Anthology search API
                                (used in daily pipeline)
  fetch_all(min_year)         — downloads anthology+abstracts.bib.gz and
                                returns ALL papers for target venues since
                                min_year (used in monthly conference sync)

No API key required for either mode.
"""
from __future__ import annotations

import gzip
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

# ACL anthology venue short ID → (canonical name, rank)
_VENUE_META: dict[str, tuple[str, str]] = {
    "acl":    ("ACL",    "A*"),
    "emnlp":  ("EMNLP",  "A*"),
    "naacl":  ("NAACL",  "A*"),
    "eacl":   ("EACL",   "A"),
    "coling": ("COLING", "A"),
    "conll":  ("CoNLL",  "A"),
    "tacl":   ("TACL",   "A"),
    "cl":     ("CL",     "A"),
    "findings": ("Findings", "A"),
}

# Venues included in fetch_all()
_DEFAULT_SYNC_VENUES = ["acl", "emnlp", "naacl", "eacl", "coling", "tacl", "findings"]
# Venues used for keyword fetch()
_DEFAULT_SEARCH_VENUES = ["acl", "emnlp", "naacl", "eacl"]

_SEARCH_URL   = "https://aclanthology.org/api/search/papers/"
_EXPORT_URL   = "https://aclanthology.org/anthology+abstracts.bib.gz"
_DELAY        = 0.5   # seconds between paginated search requests

# Minimal LaTeX accent → ASCII mapping for BibTeX parsing
_LATEX_MAP = {
    "\\'": "", '\\"': "", "\\`": "", "\\^": "", "\\~": "",
    "\\c": "", "\\v": "", "\\u": "", "\\=": "", "\\.": "",
}

def _latex_char(match: str) -> str:
    """Best-effort strip of LaTeX accent commands like {\'e} → e."""
    inner = match.strip("{}")
    for prefix, _ in _LATEX_MAP.items():
        if inner.startswith(prefix):
            return inner[len(prefix):]
    return inner


class ACLAnthologyConnector(BaseConnector):
    """Fetches papers from the ACL Anthology."""

    def __init__(
        self,
        sync_venues: list[str] | None = None,
        search_venues: list[str] | None = None,
    ) -> None:
        self._sync_venues   = sync_venues   or _DEFAULT_SYNC_VENUES
        self._search_venues = search_venues or _DEFAULT_SEARCH_VENUES

    @property
    def source_name(self) -> str:
        return "acl_anthology"

    # ── Conference-sync mode: fetch everything ────────────────────────────────

    def fetch_all(self, min_year: int = 2020) -> list[Paper]:
        """Download anthology+abstracts.bib.gz and return ALL papers for target venues.

        The export is ~37 MB compressed and includes titles, abstracts, authors,
        and BibTeX metadata for all 90,000+ ACL Anthology papers.
        Only papers from self._sync_venues and year >= min_year are returned.
        """
        log.info("[acl] downloading full anthology export from %s …", _EXPORT_URL)
        req = urllib.request.Request(
            _EXPORT_URL,
            headers={"User-Agent": "ResearchScope/1.0"},
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            compressed = resp.read()

        log.info("[acl] decompressing (%d MB compressed) …", len(compressed) // 1_000_000)
        bibtex = gzip.decompress(compressed).decode("utf-8", errors="replace")

        records = self._parse_bibtex(bibtex)
        log.info("[acl] total records in export: %d", len(records))

        papers: list[Paper] = []
        seen:   set[str]   = set()

        for record in records:
            year = self._parse_year(record.get("year", ""))
            if year < min_year:
                continue

            # Extract ACL ID from URL: https://aclanthology.org/2024.acl-long.1/
            url = record.get("url", "")
            acl_id = url.rstrip("/").split("/")[-1] if url else record.get("_key", "")
            venue_key = self._venue_key_from_id(acl_id)
            if venue_key not in self._sync_venues:
                continue

            p = self._export_record_to_paper(acl_id, record, venue_key)
            if p and p.title and p.id not in seen:
                seen.add(p.id)
                papers.append(p)

        log.info(
            "[acl] fetch_all done: %d papers (venue filter: %s, min_year: %d)",
            len(papers), self._sync_venues, min_year,
        )
        return papers

    @staticmethod
    def _parse_bibtex(bibtex: str) -> list[dict]:
        """Parse BibTeX into a list of field dicts (no external dependencies)."""
        records = []
        # Split on entry starts: @type{key,
        entry_re = re.compile(r'@\w+\{([^,]+),', re.MULTILINE)
        positions = [(m.start(), m.group(1)) for m in entry_re.finditer(bibtex)]

        for i, (start, key) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(bibtex)
            block = bibtex[start:end]

            record: dict[str, str] = {"_key": key.strip()}

            # Extract field = {value} or field = "value"
            field_re = re.compile(
                r'\n\s{4}(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|"([^"]*)")',
                re.DOTALL,
            )
            for fm in field_re.finditer(block):
                fname = fm.group(1).lower()
                fval  = (fm.group(2) or fm.group(3) or "").strip()
                # Strip simple LaTeX accents: {\'e} → e, {\"{o}} → o
                fval = re.sub(r'\{\\[^}]{1,6}\}', lambda m: _latex_char(m.group()), fval)
                fval = re.sub(r'[{}]', '', fval)
                record[fname] = fval

            records.append(record)

        return records

    # ── Daily pipeline mode: keyword search ───────────────────────────────────

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        try:
            papers = self._search(query, max_results)
            if papers:
                return papers
        except Exception as exc:
            log.debug("[acl] search API failed: %s", exc)
        try:
            return self._fallback_venue_json(max_results)
        except Exception as exc:
            log.debug("[acl] venue JSON fallback failed: %s", exc)
        return []

    # ── Search API (keyword) ──────────────────────────────────────────────────

    def _search(self, query: str, max_results: int) -> list[Paper]:
        params = urllib.parse.urlencode({"q": query, "page_size": min(max_results, 500)})
        url = f"{_SEARCH_URL}?{params}"
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "ResearchScope/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        results = (
            payload.get("results", payload.get("papers", []))
            if isinstance(payload, dict)
            else payload
        )
        return [
            p for p in (self._search_item_to_paper(r) for r in results[:max_results])
            if p.title
        ]

    def _fallback_venue_json(self, max_results: int) -> list[Paper]:
        papers: list[Paper] = []
        per_venue = max(max_results // len(self._search_venues), 5)
        for venue in self._search_venues:
            try:
                url = f"https://aclanthology.org/venues/{venue}.json"
                req = urllib.request.Request(url, headers={"User-Agent": "ResearchScope/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                items = data if isinstance(data, list) else data.get("papers", [])
                for item in items[-per_venue:]:
                    p = self._search_item_to_paper(
                        item if isinstance(item, dict) else {"acl_id": item}
                    )
                    if p.title:
                        papers.append(p)
            except Exception as exc:
                log.debug("[acl] venue fallback '%s' failed: %s", venue, exc)
        return papers

    # ── Normalise: export format ──────────────────────────────────────────────

    def _export_record_to_paper(
        self,
        paper_id: str,
        record: dict,
        venue_key: str,
    ) -> Paper | None:
        title = (record.get("title") or "").strip()
        if not title:
            return None

        # BibTeX author field: "Last, First and\n      Last, First and ..."
        raw_authors = record.get("author") or record.get("authors", "")
        if isinstance(raw_authors, str):
            normalized = re.sub(r'\s+', ' ', raw_authors)
            authors = [a.strip() for a in re.split(r'\s+and\s+', normalized) if a.strip()]
        else:
            authors = self._parse_authors(raw_authors)

        abstract = (record.get("abstract") or "").replace("\n", " ").strip()
        year     = self._parse_year(record.get("year", ""))

        venue_name, rank = _VENUE_META.get(venue_key, (venue_key.upper(), ""))

        paper_url = record.get("url") or f"https://aclanthology.org/{paper_id}"
        pdf_url   = record.get("pdf", "") or f"{paper_url}.pdf"

        return Paper(
            id=f"acl:{paper_id}",
            source=self.source_name,
            source_type="conference",
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            published_date=f"{year}-01-01" if year else "",
            venue=venue_name,
            conference_rank=rank,
            paper_url=paper_url,
            pdf_url=pdf_url,
            tags=["NLP"],
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Normalise: search API format ──────────────────────────────────────────

    def _search_item_to_paper(self, item: dict) -> Paper:
        acl_id   = item.get("acl_id", "") or item.get("id", "") or item.get("url", "")
        title    = (item.get("title") or "").strip()
        abstract = (item.get("abstract") or "").replace("\n", " ").strip()
        authors  = self._parse_authors(item.get("authors", []))
        year     = self._parse_year(str(item.get("year", "")))

        venue_raw  = item.get("venue", "") or item.get("booktitle", "") or ""
        venue_key  = self._venue_key_from_name(venue_raw)
        venue_name, rank = _VENUE_META.get(venue_key, (venue_raw or "ACL Anthology", ""))

        paper_url = f"https://aclanthology.org/{acl_id}" if acl_id else ""
        pdf_url   = item.get("pdf", "") or (f"{paper_url}.pdf" if paper_url else "")

        return Paper(
            id=f"acl:{acl_id}" if acl_id else f"acl:{abs(hash(title))}",
            source=self.source_name,
            source_type="conference",
            title=title,
            abstract=abstract,
            authors=authors,
            year=year,
            venue=venue_name,
            conference_rank=rank,
            paper_url=paper_url,
            pdf_url=pdf_url,
            tags=["NLP"],
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_year(raw: str) -> int:
        try:
            return int(str(raw).strip()[:4])
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _parse_authors(raw: list) -> list[str]:
        out = []
        for a in raw or []:
            if isinstance(a, str):
                out.append(a.strip())
            elif isinstance(a, dict):
                name = f"{a.get('first', '')} {a.get('last', '')}".strip()
                if name:
                    out.append(name)
        return out

    @staticmethod
    def _venue_key_from_id(paper_id: str) -> str:
        """Extract venue key from an anthology paper ID.

        e.g. '2024.acl-long.1'  → 'acl'
             '2024.emnlp-main.5' → 'emnlp'
             'J19-1001'          → 'cl'  (Computational Linguistics journal)
        """
        parts = paper_id.lower().split(".")
        if len(parts) >= 2:
            return parts[1].split("-")[0]
        # Legacy IDs like J19-1001, P18-1001: first letter codes venue
        prefix = parts[0][:1].lower() if parts else ""
        return {"j": "cl", "q": "tacl"}.get(prefix, "")

    @staticmethod
    def _venue_key_from_name(name: str) -> str:
        name_lower = name.lower()
        for key in _VENUE_META:
            if key in name_lower:
                return key
        return ""
