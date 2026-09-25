import gzip
import importlib.util
import json
from pathlib import Path

from src.content.generator import ContentGenerator
from src.content.llm_cache import LLMFieldCache, abstract_sha
from src.normalization.schema import Paper

ROOT = Path(__file__).resolve().parents[1]

ABSTRACT = (
    "Fiber systems suffer from chromatic dispersion. We introduce a printed "
    "achromatic lens on the fiber tip. It focuses light across 1.25-1.65 um."
)


def _paper(**kw) -> Paper:
    return Paper(id="arxiv:1", title="A metafiber", abstract=ABSTRACT, **kw)


def _entry(title="A metafiber", abstract=ABSTRACT, flags=(), **fields) -> dict:
    return {
        "id": "arxiv:1",
        "abstract_sha": abstract_sha(title, abstract),
        "model": "test",
        "prompt_version": 1,
        "flags": list(flags),
        "fields": {
            "summary": "Model summary.",
            "why_it_matters": "Model reason.",
            **fields,
        },
    }


def _write(tmp_path, *entries) -> Path:
    path = tmp_path / "llm_fields.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return path


def test_cached_fields_replace_templates(tmp_path):
    gen = ContentGenerator(LLMFieldCache.load(_write(tmp_path, _entry())))
    paper = gen.enrich(_paper())
    assert paper.summary == "Model summary."
    assert paper.why_it_matters == "Model reason."
    # Fields the cache lacks still come from the templates.
    assert paper.plain_english_explanation.startswith("In plain terms:")
    # Derived formats use the cached text too.
    assert "Model reason." in paper.newsletter_blurb


def test_changed_abstract_falls_back_to_templates(tmp_path):
    stale = _entry(abstract="An older abstract.")
    gen = ContentGenerator(LLMFieldCache.load(_write(tmp_path, stale)))
    assert gen.enrich(_paper()).summary.startswith("Fiber systems suffer")


def test_blocking_flags_are_skipped_but_soft_flags_kept(tmp_path):
    bad = _entry(flags=["numbers_not_in_abstract:summary:37%"])
    assert len(LLMFieldCache.load(_write(tmp_path, bad))) == 0
    soft = _entry(flags=["copied_from_abstract:summary"])
    assert len(LLMFieldCache.load(_write(tmp_path, soft))) == 1


def test_later_entries_win(tmp_path):
    path = _write(tmp_path, _entry(), _entry(summary="Rerun summary."))
    gen = ContentGenerator(LLMFieldCache.load(path))
    assert gen.enrich(_paper()).summary == "Rerun summary."


def test_missing_cache_file_means_templates(tmp_path):
    gen = ContentGenerator(LLMFieldCache.load(tmp_path / "absent.jsonl.gz"))
    assert gen.enrich(_paper()).summary.startswith("Fiber systems suffer")


def test_hash_matches_the_offline_script():
    spec = importlib.util.spec_from_file_location(
        "enrich", ROOT / "scripts" / "llm_enrich" / "enrich.py"
    )
    enrich = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(enrich)
    assert enrich.abstract_sha("T", ABSTRACT) == abstract_sha("T", ABSTRACT)
