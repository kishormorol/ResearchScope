<div align="center">

# ResearchScope

**Research intelligence for CS/AI papers — track what matters, who drives it, what to read first.**

Stop skimming paper lists. ResearchScope scores, tags, and surfaces the papers that actually move your field.

[![Live Site](https://img.shields.io/badge/Live%20Site-kishormorol.github.io%2FResearchScope-7c3aed?style=for-the-badge&logo=github)](https://kishormorol.github.io/ResearchScope/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Pipeline-Python%203.10%2B-3b82f6?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-f59e0b?style=for-the-badge&logo=githubactions&logoColor=white)](.github/workflows)
[![arXiv](https://img.shields.io/badge/Data-arXiv%20%2B%20Conferences-b91c1c?style=for-the-badge)](https://arxiv.org)

<br/>

![ResearchScope demo](docs/demo.gif)

</div>

---

## What is ResearchScope?

ResearchScope is an **open, static research intelligence dashboard** for computer science and AI papers. It is a website rebuilt daily by a GitHub Actions pipeline and published to GitHub Pages — no server, no sign-up, no cost.

The pipeline fetches papers from **arXiv** (all 19 cs.* categories) and **major conferences** (NeurIPS, ICML, ICLR, CVPR, ACL, and more), enriches them with multi-signal scores, detects research gaps, and writes the results as static JSON to the `site/` folder. Everything renders in the browser from those JSON files.

👉 **[Open ResearchScope](https://kishormorol.github.io/ResearchScope/)**

---

## What's New

| Date | Highlight |
|---|---|
| **Apr 2026** | **CiteLens Integration** — Every arXiv paper card now has an "🔍 Analyze citations" button that opens [CiteLens](https://kishormorol.github.io/CiteLens/) with the paper pre-loaded to see who cited it and why it mattered. |
| **Apr 2026** | **Topic Network Graph** — Interactive force-directed graph on the Topics page visualising relationships between 80+ research areas. |
| **Apr 2026** | **Institution & Author Prestige Scoring** — Papers from top labs (OpenAI, DeepMind, Google Research, MIT, Stanford…) and renowned researchers get a scoring boost. |
| **Apr 2026** | **Conference Papers Database (50K+)** — Permanent store covering NeurIPS, ICML, ICLR, CVPR, ICCV, ECCV, ACL, EMNLP, NAACL and more. Conference papers never expire. |
| **Apr 2026** | **CoRR-only arXiv Feed** — Daily arXiv updates now restricted to all 19 cs.* categories via OAI-PMH bulk fetch. Non-CS papers filtered out. |
| **Mar 2026** | **My Library** — Save papers to a browser-local personal library (localStorage). No account required. |
| **Mar 2026** | **Conference Recommender** — Paste a title and abstract to get ranked venue matches with deadlines and reviewer expectations. |

---

## Features

| Feature | Description |
|---|---|
| 📄 **Paper intelligence** | arXiv + 50K+ conference papers scored by recency, venue rank, author prestige, and novelty |
| 🔍 **Analyze citations** | One-click handoff to [CiteLens](https://kishormorol.github.io/CiteLens/) to see who cited any arXiv paper, ranked by impact |
| 👩‍🔬 **Author & lab intelligence** | Track prolific authors and their momentum scores; lab and university output profiles |
| 🗺 **Topic network graph** | Interactive graph of 80+ research areas with reading packs by difficulty |
| 🕳 **Research gap explorer** | Surface under-explored areas across 3 gap types: explicit, pattern-detected, and starter ideas |
| 🎯 **Conference recommender** | Paste title + abstract → ranked venue matches with acceptance context |
| 📚 **My Library** | Personal browser-local paper saves with FIFO ordering, persistent across reloads |
| 🖥 **Static dashboard** | Zero-backend site hosted on GitHub Pages, updated every weekday |

---

## Works with CiteLens

ResearchScope and [CiteLens](https://kishormorol.github.io/CiteLens/) are companion tools that cover the full research workflow:

```
ResearchScope  ──── "Here's a paper worth reading today"
                              │
                    🔍 Analyze citations
                              │
                              ▼
CiteLens  ──────── "Here's who cited it and why it mattered"
                              │
                    🔭 Browse topic in ResearchScope
                              │
                              ▼
ResearchScope  ──── "Discover more papers on this topic"
```

- **ResearchScope → CiteLens**: click "🔍 Analyze citations" on any arXiv paper card
- **CiteLens → ResearchScope**: click "🔭 ResearchScope" on any citing paper result

Both tools share the same `SEMANTIC_SCHOLAR_API_KEY` secret — one key covers both projects.

---

## Data Sources

| Source | Content | Update frequency |
|---|---|---|
| **arXiv (OAI-PMH)** | All cs.* preprints — 19 CoRR categories | Daily |
| **ACL Anthology** | NLP/CL papers from ACL, EMNLP, NAACL, and more | Monthly |
| **OpenReview** | ICLR, NeurIPS, COLM accepted papers | Monthly |
| **PMLR** | ICML proceedings | Monthly |
| **CVF** | CVPR, ICCV, ECCV proceedings | Monthly |
| **Semantic Scholar** | AAAI, IJCAI, CHI, SIGMOD + affiliation enrichment | Monthly |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    GitHub Actions                        │
│              (daily weekday cron schedule)               │
│                                                          │
│  src/pipeline.py  — 11 sequential stages                 │
│    ├── connectors/    arXiv · ACL · OpenReview · PMLR   │
│    │                  CVF · Semantic Scholar             │
│    ├── dedup/         Jaccard title-similarity dedup     │
│    ├── tagging/       80+ topic tags + paper_type        │
│    ├── difficulty/    L1–L4 reading level                │
│    ├── scoring/       4 scores + author momentum         │
│    ├── content/       summaries, tweets, LinkedIn posts  │
│    ├── clustering/    topic grouping                     │
│    ├── gaps/          3-layer research gap extraction    │
│    ├── aggregation/   author, lab, university profiles   │
│    └── sitegen/       → data/*.json + site/data/*.json  │
└──────────────────────────┬──────────────────────────────┘
                           │ commits data/ + deploys site/
                           ▼
                  site/  (GitHub Pages)
                    index.html          – homepage + Paper of the Day
                    papers.html         – full paper list
                    topics.html         – 80-topic browser + network graph
                    authors.html        – author profiles
                    labs.html           – lab + university profiles
                    gaps.html           – research gap explorer
                    conferences.html    – conference paper browser
                    deadlines.html      – upcoming submission deadlines
                    digest.html         – weekly curated digest
                    library.html        – My Library (localStorage)
                    conference-recommender.html
                    search.html         – full-text search
```

---

## Project Layout

```
.github/workflows/
  update.yml              # daily pipeline + Pages deploy (weekdays)
  conference-sync.yml     # monthly full conference sync
  backfill.yml            # manual historical backfill
  discord-potd.yml        # daily Paper of the Day → Discord
src/
  pipeline.py             # 11-stage orchestrator
  connectors/             # arXiv, ACL, OpenReview, PMLR, CVF, S2
  dedup/                  # Jaccard title deduplication
  tagging/                # 80+ topic tags + paper_type
  difficulty/             # L1–L4 difficulty assessor
  scoring/                # 4 scores + author momentum scorer
  content/                # rule-based content enrichment
  clustering/             # topic clustering
  gaps/                   # 3-layer gap extractor
  aggregation/            # author, lab, university builder
  sitegen/                # JSON writer + conference recommender
site/
  index.html              # homepage
  papers.html             # paper list with score breakdowns
  topics.html             # topic browser + interactive network graph
  authors.html / labs.html / gaps.html / conferences.html
  deadlines.html / digest.html / library.html / search.html
  conference-recommender.html
  assets/css/ assets/js/
config/
  topics.yaml             # 24-entry topic taxonomy
  weights.yaml            # tuneable score weights
  venues.yaml             # conference registry with ranks
data/                     # generated JSON (committed by CI)
tests/                    # pytest suite (110+ tests)
```

---

## Local Development

```bash
# Clone and install
git clone https://github.com/kishormorol/ResearchScope.git
cd ResearchScope

python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run the pipeline locally (writes JSON to data/)
python src/pipeline.py

# Run tests
python -m pytest tests/ -v

# Serve the site locally
cd site && python -m http.server 8080
```

### Environment variables

| Variable | Description |
|---|---|
| `SEMANTIC_SCHOLAR_API_KEY` | Optional. Raises S2 rate limit from 1 req/s to 10 req/s. Add as a GitHub Actions secret. |

---

## GitHub Pages Deployment

The workflow in `.github/workflows/update.yml`:

1. Runs the Python pipeline to fetch and process papers.
2. Commits updated JSON files to `data/`.
3. Uploads the `site/` folder as a GitHub Pages artifact and deploys it.

To enable Pages for a fork: go to **Settings → Pages** and set the source to **GitHub Actions**.

---

## Alternatives comparison

| Tool | Free | Open source | Daily updates | Research gaps | Conference deadlines | No sign-up |
|---|---|---|---|---|---|---|
| **ResearchScope** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Arxiv Sanity](https://arxiv-sanity-lite.com) | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| [Papers With Code](https://paperswithcode.com) | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| [Semantic Scholar](https://semanticscholar.org) | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| [Elicit](https://elicit.com) | Partial | ❌ | ❌ | ❌ | ❌ | ❌ |
| [Consensus](https://consensus.app) | Partial | ❌ | ❌ | ❌ | ❌ | ❌ |

ResearchScope is the only fully free, open-source dashboard that combines **daily paper rankings, research gap detection, conference deadlines, and citation analysis** in one place — with zero backend.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Acknowledgments

| Source | What we use | License |
|---|---|---|
| [arXiv](https://arxiv.org) | Paper metadata via OAI-PMH | Metadata: CC0 (public domain) |
| [ACL Anthology](https://aclanthology.org) | NLP/CL paper metadata | 2016+: CC BY 4.0 |
| [PMLR](https://proceedings.mlr.press) | ICML proceedings metadata | CC BY 4.0 |
| [Semantic Scholar](https://www.semanticscholar.org) | Conference metadata + affiliations | [S2 API License](https://www.semanticscholar.org/product/api/license) |
| [OpenReview](https://openreview.net) | ICLR, NeurIPS, COLM papers | Public API |
| [CVF](https://openaccess.thecvf.com) | CVPR, ICCV, ECCV papers | Public access |

ResearchScope stores only bibliographic metadata. No full text or PDFs are stored or redistributed.

---

## Contributors

[![Contributors](https://contrib.rocks/image?repo=kishormorol/ResearchScope)](https://github.com/kishormorol/ResearchScope/graphs/contributors)

| Contributor | GitHub | Role |
|---|---|---|
| Md Kishor Morol | [@kishormorol](https://github.com/kishormorol) | Project lead · architecture · pipeline |
| Shadril Hassan | [@shadril238](https://github.com/shadril238) | Topic network graph |
| Saad Chowdhury | [@0Sa-ad0](https://github.com/0Sa-ad0) | Contributor |

Want to contribute? See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT © 2026 Md Kishor Morol
