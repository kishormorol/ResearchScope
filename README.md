# 🔭 ResearchScope

**Open-source research intelligence for CS papers** — track what matters, who drives it, what to read first, and where the research gaps are.

[![Update Data & Deploy Pages](https://github.com/ResearchScope/ResearchScope/actions/workflows/update.yml/badge.svg)](https://github.com/ResearchScope/ResearchScope/actions/workflows/update.yml)

---

## Overview

ResearchScope is a static-first platform that aggregates papers from **arXiv** and **ACL Anthology**, scores them by relevance, detects emerging topics, and surfaces research gaps — all updated daily via GitHub Actions and served from GitHub Pages with zero backend costs.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     GitHub Actions                       │
│  (daily cron: 02:00 UTC + manual workflow_dispatch)      │
└───────────────────────┬─────────────────────────────────┘
                        │  python src/pipeline.py
          ┌─────────────▼─────────────┐
          │        Pipeline           │
          │  ┌──────────────────────┐ │
          │  │  Connectors          │ │
          │  │  · ArxivConnector    │ │
          │  │  · ACLConnector      │ │
          │  └────────┬─────────────┘ │
          │  ┌────────▼─────────────┐ │
          │  │  Normalization       │ │
          │  │  (Paper / Author /   │ │
          │  │   Topic / Gap)       │ │
          │  └────────┬─────────────┘ │
          │  ┌────────▼─────────────┐ │
          │  │  Processing          │ │
          │  │  · Deduplication     │ │
          │  │  · Scoring           │ │
          │  │  · Tagging           │ │
          │  │  · Difficulty        │ │
          │  │  · Clustering        │ │
          │  │  · Gap Extraction    │ │
          │  │  · Content Gen       │ │
          │  └────────┬─────────────┘ │
          │  ┌────────▼─────────────┐ │
          │  │  SiteGenerator       │ │
          │  │  → data/*.json       │ │
          │  └──────────────────────┘ │
          └───────────────────────────┘
                        │
          ┌─────────────▼─────────────┐
          │     GitHub Pages          │
          │  site/  (static HTML/JS)  │
          │  · index.html             │
          │  · papers.html            │
          │  · topics.html            │
          │  · conferences.html       │
          │  · authors.html           │
          │  · labs.html              │
          │  · gaps.html              │
          └───────────────────────────┘
```

---

## Directory Structure

```
ResearchScope/
├── src/
│   ├── connectors/       # Data source connectors (arXiv, ACL)
│   ├── normalization/    # Schema dataclasses (Paper, Author, Topic, …)
│   ├── dedup/            # Deduplication
│   ├── scoring/          # Paper relevance scoring
│   ├── tagging/          # Keyword-based topic tagging
│   ├── difficulty/       # Difficulty assessment
│   ├── clustering/       # Topic clustering
│   ├── gaps/             # Research gap extraction
│   ├── content/          # Content generation helpers
│   ├── sitegen/          # JSON site data writer
│   └── pipeline.py       # Main pipeline entry point
├── site/                 # Static frontend (GitHub Pages)
│   ├── index.html
│   ├── papers.html
│   ├── topics.html
│   ├── conferences.html
│   ├── authors.html
│   ├── labs.html
│   ├── gaps.html
│   └── assets/
│       ├── css/style.css
│       └── js/app.js
├── data/                 # Generated JSON (gitignored, except .gitkeep)
├── tests/                # pytest test suite
├── .github/workflows/    # CI/CD: daily update + Pages deploy
├── requirements.txt
└── pyproject.toml
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/ResearchScope/ResearchScope.git
cd ResearchScope
pip install -r requirements.txt
```

### 2. Run the pipeline locally

```bash
PYTHONPATH=. python src/pipeline.py
```

This fetches papers from arXiv and ACL Anthology and writes JSON files to `data/`.

### 3. Serve the site locally

```bash
cd site
python -m http.server 8000
# Open http://localhost:8000
```

### 4. Run tests

```bash
pytest
```

---

## Pipeline Components

| Module | Description |
|--------|-------------|
| `src/connectors/arxiv_connector.py` | Fetches papers from arXiv Atom API |
| `src/connectors/acl_connector.py` | Fetches papers from ACL Anthology API |
| `src/dedup/deduplicator.py` | Jaccard-similarity title deduplication |
| `src/scoring/scorer.py` | Recency + citation + completeness scoring |
| `src/tagging/tagger.py` | Regex keyword → topic tag mapping |
| `src/difficulty/assessor.py` | beginner / intermediate / advanced classification |
| `src/clustering/clusterer.py` | Groups papers by tag into Topic objects |
| `src/gaps/gap_extractor.py` | Extracts research gaps from abstracts |
| `src/content/generator.py` | Generates summaries and "why it matters" blurbs |
| `src/sitegen/generator.py` | Writes `data/*.json` for the frontend |

---

## GitHub Actions

The workflow at `.github/workflows/update.yml` runs daily at 02:00 UTC:

1. **`update-data`** — runs the pipeline and commits any changed `data/*.json`
2. **`deploy-pages`** — deploys `site/` to GitHub Pages

To enable GitHub Pages deployment:
1. Go to **Settings → Pages**
2. Set **Source** to **GitHub Actions**

---

## Contributing

Contributions are welcome! Here's how to get started:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-improvement`
3. Make your changes and add tests
4. Run the test suite: `pytest`
5. Open a pull request

### Adding a new connector

1. Create `src/connectors/my_connector.py`
2. Subclass `BaseConnector` and implement `fetch()` and `source_name`
3. Register it in `src/pipeline.py`

### Adding new tags / topics

Edit the `_RULES` list in `src/tagging/tagger.py`.

---

## License

MIT — see [LICENSE](LICENSE).

