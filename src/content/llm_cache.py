"""Model-written paper fields, produced offline by scripts/llm_enrich/enrich.py.

ContentGenerator fills five reader-facing fields from templates. When this cache has
a clean entry for a paper, those fields come from here instead. An entry is used only
while its abstract hash matches the paper's current title and abstract, so a revised
abstract falls back to the templates until the paper is re-enriched.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "llm_fields.jsonl.gz"

FIELDS = (
    "summary",
    "key_contribution",
    "one_line_takeaway",
    "plain_english_explanation",
    "why_it_matters",
)

# Flags that make an entry unusable. Others (e.g. copied_from_abstract) are kept:
# they are worth a look but are not wrong.
BLOCKING = ("invalid_json", "empty:", "numbers_not_in_abstract:")


def abstract_sha(title: str, abstract: str) -> str:
    """Must match scripts/llm_enrich/enrich.py, which runs outside this package."""
    return hashlib.sha256(f"{title}\n{abstract}".encode()).hexdigest()[:16]


class LLMFieldCache:
    def __init__(self, entries: dict[str, dict] | None = None):
        self._entries = entries or {}

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> LLMFieldCache:
        path = Path(path)
        if not path.exists():
            return cls()
        opener = gzip.open if path.suffix == ".gz" else open
        entries: dict[str, dict] = {}
        skipped = 0
        with opener(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                e = json.loads(line)
                if any(f.startswith(BLOCKING) for f in e.get("flags", [])):
                    skipped += 1
                    continue
                entries[e["id"]] = e  # later lines win: re-runs replace earlier output
        log.info(
            "[llm] %d cached paper fields (%d flagged entries skipped)",
            len(entries),
            skipped,
        )
        return cls(entries)

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, paper_id: str, title: str, abstract: str, field: str) -> str | None:
        e = self._entries.get(paper_id)
        if not e or e.get("abstract_sha") != abstract_sha(title, abstract):
            return None
        return (e.get("fields") or {}).get(field) or None
