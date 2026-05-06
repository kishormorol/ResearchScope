<div align="center">

# ResearchScope

**Research intelligence for CS/AI papers — track what matters, who drives it, what to read first.**

Stop skimming paper lists. ResearchScope scores, tags, and surfaces the papers that actually move your field.

[![Live Site](https://img.shields.io/badge/Live%20Site-kishormorol.github.io%2FResearchScope-7c3aed?style=for-the-badge&logo=github)](https://kishormorol.github.io/ResearchScope/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Pipeline-Python%203.10%2B-3b82f6?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-f59e0b?style=for-the-badge&logo=githubactions&logoColor=white)](.github/workflows)
[![arXiv](https://img.shields.io/badge/Data-arXiv%20%2B%20Conferences-b91c1c?style=for-the-badge)](https://arxiv.org)
[![Supabase](https://img.shields.io/badge/Database-Supabase-3ecf8e?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)

<br/>

![ResearchScope demo](docs/demo.gif)

</div>

---

## What is ResearchScope?

ResearchScope is an **open research intelligence dashboard** for computer science and AI papers. A GitHub Actions pipeline runs daily, fetches papers from **arXiv** (all 19 cs.* categories) and **major conferences** (NeurIPS, ICML, ICLR, CVPR, ACL, and more), enriches them with multi-signal scores, detects research gaps, and persists everything to a **Supabase PostgreSQL database**. The frontend is hosted on GitHub Pages and queries Supabase directly — no file-size caps, no rolling windows, no limits.

👉 **[Open ResearchScope](https://kishormorol.github.io/ResearchScope/)**

---

## What's New

| Date | Highlight |
|---|---|
| **May 2026** | **Supabase Backend** — All 17,500+ papers, authors, topics, gaps, and labs now live in a Supabase PostgreSQL database. Every page queries Supabase directly — no file-size caps, no rolling windows. The full dataset is always browsable. |
| **May 2026** | **Full Dataset Access** — The papers browser now shows all papers with server-side filtering and pagination (previously capped at 1,000). Search covers the entire database live. |
| **Apr 2026** | **CiteLens Integration** — Every arXiv paper card now has an "🔍 Analyze citations" button that opens [CiteLens](https://kishormorol.github.io/CiteLens/) with the paper pre-loaded to see who cited it and why it mattered. |
| **Apr 2026** | **Topic Network Graph** — Interactive force-directed graph on the Topics page visualising relationships between 80+ research areas. |
| **Apr 2026** | **Institution & Author Prestige Scoring** — Papers from top labs (OpenAI, DeepMind, Google Research, MIT, Stanford…) and renowned researchers get a scoring boost. |
| **Apr 2026** | **Conference Papers Database** — Permanent store covering NeurIPS, ICML, ICLR, CVPR, ICCV, ECCV, ACL, EMNLP, NAACL and more. Conference papers never expire. |
| **Mar 2026** | **My Library** — Save papers to a browser-local personal library (localStorage). No account required. |
| **Mar 2026** | **Conference Recommender** — Paste a title and abstract to get ranked venue matches with deadlines and reviewer expectations. |

---

## Features

| Feature | Description |
|---|---|
| 📄 **Paper intelligence** | 17,500+ arXiv + conference papers scored by recency, venue rank, author prestige, and novelty |
| 🗄 **Supabase backend** | Full dataset stored in PostgreSQL — no caps, no rolling windows, server-side filtering and search |
| 🔍 **Analyze citations** | One-click handoff to [CiteLens](https://kishormorol.github.io/CiteLens/) to see who cited any arXiv paper, ranked by impact |
| 👩‍🔬 **Author & lab intelligence** | Track 5,000+ prolific authors and their momentum scores; lab and university output profiles |
| 🗺 **Topic network graph** | Interactive graph of 80+ research areas with reading packs by difficulty |
| 🕳 **Research gap explorer** | Surface under-explored areas across 3 gap types: explicit, pattern-detected, and starter ideas |
| 🎯 **Conference recommender** | Paste title + abstract → ranked venue matches with acceptance context |
| 📚 **My Library** | Personal browser-local paper saves with FIFO ordering, persistent across reloads |
| ⚡ **Live search** | Global search queries Supabase directly — results from the full 17,500+ paper dataset |

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
│         (daily weekdays + monthly conference sync)       │
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
│    └── sitegen/       → data/*.json + Supabase upsert   │
└───────────────┬──────────────────────┬──────────────────┘
                │ commits + deploys    │ upserts all data
                ▼                      ▼
       site/ (GitHub Pages)     Supabase PostgreSQL
         index.html               papers       (17,500+, no cap)
         papers.html              authors      (5,000+)
         topics.html              topics       (150+)
         authors.html             gaps         (100+)
         labs.html                labs         (unlimited)
         gaps.html
         conferences.html                ▲
         deadlines.html                  │ REST API (anon key)
         digest.html                     │
         library.html            Frontend queries Supabase
         search.html             directly for all live data
         conference-recommender.html
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
  storage/
    supabase_store.py     # upserts all data to Supabase after each run
supabase/
  schema.sql              # PostgreSQL schema (run once in Supabase dashboard)
scripts/
  discord_potd.py         # Paper of the Day → Discord webhook
  migrate_to_supabase.py  # one-time migration of existing JSON data
site/
  index.html              # homepage
  papers.html             # paper browser — queries Supabase (all papers)
  topics.html             # topic browser + interactive network graph
  authors.html / labs.html / gaps.html / conferences.html
  deadlines.html / digest.html / library.html / search.html
  conference-recommender.html
  assets/css/
  assets/js/
    app.js                # shared utilities
    supabase-client.js    # Supabase query helpers (anon key, public)
    library.js / library-page.js / topic-graph.js
config/
  topics.yaml             # topic taxonomy
  weights.yaml            # tuneable score weights
  venues.yaml             # conference registry with ranks
data/                     # generated JSON (committed by CI, fast fallback)
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

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | Yes | Your Supabase project URL (e.g. `https://xxx.supabase.co`). Add as a GitHub Actions secret. |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key — grants write access for the pipeline. Add as a GitHub Actions secret. |
| `SUPABASE_ANON_KEY` | Frontend only | Public anon key used by the browser. Already embedded in `supabase-client.js`. |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional | Raises S2 rate limit from 1 req/s to 10 req/s. Add as a GitHub Actions secret. |
| `OPENAI_API_KEY` | Optional | Enables AI-generated summaries and content fields. |
| `ANTHROPIC_API_KEY` | Optional | Alternative to OpenAI for content generation. |
| `DISCORD_WEBHOOK_URL` | Optional | Enables daily Paper of the Day posts to a Discord channel. |

### Setting up Supabase

1. Create a free project at [supabase.com](https://supabase.com).
2. Go to **SQL Editor** and run the contents of `supabase/schema.sql` to create all tables.
3. Add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as GitHub Actions secrets.
4. Run the one-time migration to populate existing data:
   ```bash
   pip install supabase
   export SUPABASE_URL=https://xxx.supabase.co
   export SUPABASE_SERVICE_ROLE_KEY=eyJ...
   python scripts/migrate_to_supabase.py
   ```

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

ResearchScope is the only fully free, open-source dashboard that combines **daily paper rankings, research gap detection, conference deadlines, and citation analysis** in one place — backed by a real database with no paper caps.

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
