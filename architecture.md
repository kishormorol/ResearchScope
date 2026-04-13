# ResearchScope — Architecture

## Overview

ResearchScope is a **static-first research intelligence platform**. The entire backend runs as a scheduled batch job (GitHub Actions). The output is a set of JSON files hosted alongside static HTML on GitHub Pages — no always-on server required.

```
┌──────────────────────────────────────────────────────────────────┐
│                        GitHub Actions                            │
│                  (runs daily at 02:00 UTC)                       │
│                                                                  │
│  python src/pipeline.py                                          │
│    │                                                             │
│    ├── Stage 1  Fetch        ← connectors/                       │
│    ├── Stage 2  Dedup        ← dedup/                            │
│    ├── Stage 3  Tag          ← tagging/                          │
│    ├── Stage 4  Difficulty   ← difficulty/                       │
│    ├── Stage 5  Score        ← scoring/                          │
│    ├── Stage 6  Enrich       ← content/                          │
│    ├── Stage 7  Cluster      ← clustering/                       │
│    ├── Stage 8  Gaps         ← gaps/                             │
│    ├── Stage 9  Aggregate    ← aggregation/                      │
│    ├── Stage 10 Editorial    ← content/                          │
│    └── Stage 11 Site gen     ← sitegen/                          │
│                                                                  │
│  Writes: data/*.json → site/data/*.json                          │
└──────────────────────────────────────────────────────────────────┘
                            │ GitHub Pages
                            ▼
                     site/  (published)
                       index.html, papers.html, …
                       data/papers.json, …
```

---

## Data Flow

```
Source API  →  Connector  →  Paper (raw)
                              │
                          Deduplicator   (removes near-duplicates)
                              │
                           PaperTagger   (tags + paper_type)
                              │
                        DifficultyAssessor  (L1–L4)
                              │
                          PaperScorer   (4 scores + breakdown)
                              │
                        ContentGenerator  (summaries, creator outputs)
                              │
                        TopicClusterer  (Topic objects)
                              │
                          GapExtractor  (3-layer gaps)
                              │
                           Aggregator   (Author, Lab, University)
                              │
                        EditorialQueue  (daily digest)
                              │
                         SiteGenerator  → data/*.json
```

---

## Source Connector Architecture

All connectors inherit from `BaseConnector`:

```python
class BaseConnector(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    def fetch(self, query: str, max_results: int) -> list[Paper]: ...
```

Each connector is responsible for:
- Fetching raw records from its source
- Mapping to the normalised `Paper` schema
- Setting `source`, `source_type`, `venue`, `conference_rank`

**Current connectors:**
| Connector | Source | Method |
|---|---|---|
| `ArxivConnector` | arXiv | `arxiv` package + Atom API fallback |
| `ACLAnthologyConnector` | ACL Anthology | Search API + venue JSON fallback |

**Planned connectors:**
| Connector | Source |
|---|---|
| `OpenReviewConnector` | ICLR, NeurIPS, ICML, COLM |
| `ProceedingsMLRConnector` | ICML PMLR proceedings |
| `SemanticScholarConnector` | Enriches citations |

---

## Normalised Schema

The `Paper` dataclass in `src/normalization/schema.py` is the single shared data model. Key design decisions:

- All fields have safe defaults (no required fields) so connectors can populate what they know
- `canonical_id` is separate from `id` — same research work may appear as arXiv preprint and later as conference paper
- `score_breakdown` is a nested dict storing component-level scores for transparency
- Backward-compat properties (`url`, `difficulty`) are computed from canonical fields

---

## Scoring System

Four independent scores, each 0–10:

| Score | Purpose | Key components |
|---|---|---|
| `paper_score` | What matters | recency, novelty, quality_hint, completeness |
| `read_first_score` | What to read first | clarity, foundational value, accessibility, topic centrality |
| `content_potential_score` | Worth discussing publicly | surprise, practical value, explainability, broad relevance |
| `momentum_score` | Author / lab trajectory | recent output, avg quality, acceleration |

All weights are configurable in `config/weights.yaml`.

---

## Research Gap Engine

Three gap layers:

| Layer | Type | Confidence |
|---|---|---|
| 1 | Explicit | ~0.8 — direct from limitations/future-work language |
| 2 | Pattern | ~0.4–0.9 — recurring weakness across papers |
| 3 | Starter | ~0.7 — beginner-friendly research ideas |

---

## Static Deployment

1. GitHub Actions runs `python src/pipeline.py`
2. Pipeline writes `data/*.json`
3. Workflow copies JSON into `site/data/`
4. Workflow uploads `site/` as a GitHub Pages artifact
5. GitHub Pages serves `site/` at `https://{user}.github.io/ResearchScope/`

The site loads JSON at runtime via `fetch()` and renders entirely client-side. No build step required.

---

## Adding a New Conference Source

1. Create `src/connectors/{name}_connector.py` subclassing `BaseConnector`
2. Set `source_type="conference"`, populate `venue` and `conference_rank`
3. Add the venue to `config/venues.yaml`
4. Import and add the connector to `run_pipeline()` in `src/pipeline.py`

No other changes are needed — the rest of the pipeline is source-agnostic.

---

## Directory Structure

```
/.github/workflows/update.yml    — daily pipeline + Pages deploy
/config/
  venues.yaml                    — conference registry + rankings
  weights.yaml                   — score weight config
  topics.yaml                    — topic taxonomy
/data/                           — generated JSON (committed by CI)
/site/
  index.html, papers.html, …     — static frontend
  assets/css/, assets/js/        — shared styles + JS
  data/                          — copy of /data/ for Pages
/src/
  pipeline.py                    — orchestrator
  connectors/                    — data source connectors
  normalization/schema.py        — shared data model
  dedup/                         — deduplication
  tagging/                       — topic tags + paper type
  difficulty/                    — L1–L4 difficulty
  scoring/                       — four scoring systems
  clustering/                    — topic clusters
  gaps/                          — research gap engine
  content/                       — content + editorial
  aggregation/                   — author/lab/university
  sitegen/                       — JSON writer
/tests/                          — pytest test suite
```
