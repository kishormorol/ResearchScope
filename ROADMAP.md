# ResearchScope — Roadmap

## v0.1 — MVP (current)

**Data sources:**
- [x] arXiv preprints (via `arxiv` package + Atom API fallback)
- [x] ACL Anthology (search API + venue JSON fallback)

**Intelligence pipeline:**
- [x] Normalised Paper/Author/Lab/University schema
- [x] Near-duplicate detection (Jaccard title similarity)
- [x] Keyword-based topic tagging (25+ topics)
- [x] Paper type detection (survey, benchmark, dataset, methods, …)
- [x] L1–L4 difficulty classification with plain-English reason
- [x] 4-score system: paper_score, read_first_score, content_potential, momentum
- [x] Score breakdowns + transparent reasoning
- [x] Author aggregation with momentum scoring
- [x] Lab / industry aggregation
- [x] University aggregation
- [x] 3-layer research gap engine (explicit, pattern, starter)
- [x] Creator content generation (tweet, LinkedIn, newsletter, video script)
- [x] Daily editorial queue

**Frontend:**
- [x] Homepage with stats, top papers, editorial digest
- [x] Papers page (filterable, sortable, score breakdown)
- [x] Topics page (reading paths, starter/frontier packs)
- [x] Research Gaps page (3 gap types, starter ideas)
- [x] Authors page (momentum, topics, profile)
- [x] Labs & Universities page (output, momentum)
- [x] Conferences page
- [x] Dark mode

**Infrastructure:**
- [x] GitHub Actions daily pipeline
- [x] GitHub Pages static deployment
- [x] Config-driven weights and venues

---

## v0.2 — Conference Expansion

- [ ] **OpenReview connector** — ICLR, NeurIPS, ICML, COLM (oral/poster/reject signals)
- [ ] **PMLR connector** — ICML proceedings
- [ ] Per-conference explorer pages with theme detection
- [ ] Best paper award tracking
- [ ] Acceptance rate context per venue
- [ ] Conference comparison view

---

## v0.3 — Semantic Intelligence

- [ ] **Sentence-transformer embeddings** for semantic dedup and clustering
  - Replace Jaccard with cosine similarity
  - Better topic clustering beyond keywords
- [ ] **Citation network** via Semantic Scholar API
  - Real citation counts
  - Influential citations
  - Paper ancestry / descendant graphs
- [ ] **Paper lifecycle tracking**
  - Link arXiv preprint → accepted conference version
  - "First seen / accepted at" timeline
  - Maturity stage auto-classification

---

## v0.4 — LLM Enrichment (optional)

- [ ] Optional LLM-powered enrichment stage (requires API key)
  - Better summaries from full PDF text
  - Richer "why it matters" explanations
  - Automatic limitations extraction from PDFs
- [ ] PDF parsing via `pymupdf4llm` or similar
- [ ] Preserve rule-based fallback when no API key is set

---

## v0.5 — Learning System

- [ ] Curated reading paths per topic (hand-edited + auto-generated)
- [ ] Prerequisites graph visualisation
- [ ] "Start here" vs "Go deeper" track separation
- [ ] Paper difficulty quiz / self-assessment
- [ ] User reading history (localStorage)

---

## v0.6 — Creator Tools

- [ ] Creator dashboard — per-paper content package download
- [ ] Email newsletter template export
- [ ] Slides outline generator
- [ ] "Explain to non-expert" generator

---

## v0.7 — Community & Personalisation

- [ ] Topic subscriptions (RSS feed per topic)
- [ ] Custom watchlists (stored in localStorage)
- [ ] "Papers like this one" recommendations
- [ ] Author follow + alert

---

## Future Conference Connectors

| Conference | Area | Status |
|---|---|---|
| ICLR | ML | Planned (v0.2) |
| NeurIPS | ML | Planned (v0.2) |
| ICML | ML | Planned (v0.2) |
| COLM | LM | Planned (v0.2) |
| CVPR | CV | Planned |
| ICCV | CV | Planned |
| ECCV | CV | Planned |
| CHI | HCI | Planned |
| SIGIR | IR | Planned |
| AAAI | AI | Planned |
| IJCAI | AI | Planned |
| WWW | Web | Planned |

---

## Known Limitations (MVP)

- Affiliation extraction is heuristic (keyword matching) — no ground-truth author-institution database
- Deduplication uses title Jaccard similarity — may miss paraphrased titles
- All tagging and difficulty are rule-based — LLM enrichment planned for v0.4
- ACL search API availability is not guaranteed — falls back gracefully to empty
- No persistent state between pipeline runs (each run is a full refresh)
