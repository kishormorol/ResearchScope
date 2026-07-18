# Chat with Paper

## Current status

Chat with Paper is an implemented, authenticated ResearchScope feature for arXiv papers. It provides a split workspace with a PDF reader on the left and an evidence-grounded assistant on the right.

The feature currently uses:

- a dedicated `Chat arXiv` navigation entry and discovery page;
- a PDF.js reader with page navigation, zoom, fit-width, and citation jumps;
- PostgreSQL-backed document chunks and per-user chat history;
- structured PDF extraction with PyMuPDF;
- OpenAI embeddings and the OpenAI Responses API;
- hybrid lexical and semantic retrieval with validated page citations.

Normal ResearchScope paper-title links remain external paper/source links. They do not automatically open the chat workspace. Chat is intentionally accessed through the separate Chat arXiv section.

## User flow

1. Open `/chat-arxiv` from the main navigation.
2. Search the indexed ResearchScope arXiv catalog by title or keyword, select a listed paper, or paste a supported arXiv ID/URL.
3. ResearchScope opens `/chat-paper?id=<encoded-paper-id>`.
4. The PDF begins loading in the left reader.
5. If the user is signed in, the backend checks whether a current knowledge base already exists for that paper.
6. A cached current knowledge base is reused immediately. Otherwise, the backend downloads, extracts, chunks, embeds, and indexes the PDF.
7. The assistant becomes available when document status is `ready`.
8. Answers are returned with validated source labels and clickable page citations.

Guests can open the workspace and view an available PDF. Sign-in is required to prepare the document, send messages, and access saved history.

The loading overlay combines two signals:

- PDF download percentage reported by PDF.js;
- phase-based context-preparation progress derived from backend status polling.

The PDF percentage reflects real download progress. Context percentage communicates the current phase; it is not byte-level extraction progress.

## Frontend architecture

### Entry and discovery

- `site/chat-arxiv.html` contains the arXiv discovery screen.
- `site/assets/js/chat-arxiv.js` handles search results, keyboard navigation, featured papers, and workspace links.
- `site/assets/js/chat-arxiv-core.js` normalizes arXiv IDs/URLs and builds safe workspace URLs.
- Keyword search uses the ResearchScope `/search` catalog endpoint and filters results to arXiv papers. It is not a live search of every paper on arXiv.org.

### Paper workspace

- `site/chat-paper.html` defines the responsive PDF/assistant workspace.
- `site/assets/js/chat-paper.js` coordinates paper metadata, PDF loading, preparation polling, sessions, history, SSE responses, citations, and mobile tabs.
- `site/assets/js/paper-pdf-viewer.js` provides the PDF.js reader.
- `site/assets/js/chat-paper-core.js` contains reusable URL, SSE, and state helpers.
- `site/assets/css/chat-paper.css` and `site/assets/css/chat-arxiv.css` keep the pages aligned with the ResearchScope theme.

Desktop uses a split layout. Smaller screens switch between Paper and Assistant tabs while retaining the independent view state.

Citation chips call the PDF reader with the cited page number. If the embedded reader cannot load the document, the workspace exposes an external PDF action.

### API base behavior

`site/assets/js/railway-api.js` selects API targets as follows:

- localhost auth, paper-specific, preparation, and chat requests use `http://127.0.0.1:8000`;
- localhost public `/papers` and `/search` catalog requests use the same-origin proxy exposed by `scripts/serve_site.py` and backed by production Railway data;
- deployed pages use the Railway API directly.

`window.__RS_API_BASE__` and `window.__RS_PAPERS_LIST_API_BASE__` can override these defaults before the API client loads.

## Backend architecture

The backend is a FastAPI service backed by PostgreSQL.

Main modules:

- `backend/app/routers/papers.py`: paper metadata, viewer URL, and PDF proxy endpoints;
- `backend/app/routers/paper_documents.py`: authenticated preparation status and queueing;
- `backend/app/routers/chat.py`: authenticated session, history, deletion, and streaming endpoints;
- `backend/app/services/document_service.py`: secure PDF resolution/download, extraction, chunking, embedding, and persistence;
- `backend/app/services/retrieval_service.py`: query routing and hybrid retrieval;
- `backend/app/services/chat_service.py`: limits, prompting, evidence validation, persistence, and SSE events;
- `backend/app/services/provider_service.py`: OpenAI Responses and Embeddings API calls;
- `backend/app/services/paper_catalog_service.py`: trusted metadata fallback for papers missing from the local database;
- `backend/app/services/paper_viewer_service.py`: browser-viewable PDF resolution.

## Knowledge-base preparation

### 1. Paper and PDF resolution

The backend resolves the requested paper from the trusted PostgreSQL paper record. When configured, `PAPER_CATALOG_FALLBACK_URL` can import one validated paper record into a local database on a cache miss.

The PDF URL is derived from trusted metadata or a supported source-specific pattern. Preparation accepts HTTPS only and applies:

- a host allowlist;
- public-IP DNS validation to block private-network access;
- redirect validation with a maximum of four requests;
- connection and total timeouts;
- a default 15 MB size limit;
- a `%PDF-` content-signature check.

Validated browser-safe HTTPS URLs are returned directly by default, avoiding
unnecessary backend bandwidth and memory. When the proxy is required, concurrent
downloads of the same PDF share one fetch and the result is kept in a bounded,
time-limited process cache. PDF bytes are not stored in PostgreSQL or on disk.
The proxy supports `Range`, `Content-Range`, `ETag`, and streamed 64 KiB response
chunks for PDF.js and browser seeking.

### 2. Structured extraction

The current extractor version is `pymupdf-hybrid-v2`.

PyMuPDF reads page blocks in visual order and records:

- page number;
- normalized text;
- section heading when detected;
- content type, including paragraph, table, or figure context;
- bounding box coordinates.

The extracted text must contain sufficient usable content. Scanned or otherwise text-inaccessible PDFs fail preparation instead of falling back to the abstract.

### 3. Parent/child chunking

Each page is organized into section-aware groups and split into two levels:

- parent chunks: default target of 1,500 tokens, used for broader context;
- child chunks: default target of 600 tokens with 100-token overlap, used for focused retrieval.

Parent/child links, page numbers, section names, content types, token counts, and bounding boxes are stored with every chunk.

### 4. Embeddings and lexical index

When `CHAT_EMBEDDINGS_ENABLED=true`, child chunks are embedded in batches through the OpenAI Embeddings API. The current defaults are:

- model: `text-embedding-3-large`;
- dimensions: `256`;
- batch size: `32`.

Vectors remain stored as PostgreSQL `REAL[]` for zero-data-loss compatibility.
Cosine ranking runs inside PostgreSQL instead of loading every embedding into
Python. When pgvector is available, startup also creates an HNSW expression index
for the default 256-dimension embeddings. PostgreSQL maintains an English
`tsvector` search index for every chunk as well.

### 5. Persistence and PDF disposal

After successful extraction and embedding, the backend stores the document metadata and chunks, marks the document `ready`, and releases the in-memory PDF bytes.

## Chunk reuse and rebuilding

Chunks are not recreated every time a user opens a paper or asks a question.

There is one `paper_documents` row per paper and one shared set of `paper_chunks` for that paper. All users reuse that prepared knowledge base.

Preparation is idempotent:

- if status is `ready` and the extractor/embedding configuration is current, the existing chunks are reused;
- if another preparation is active and younger than 15 minutes, a duplicate job is not started;
- stale preparation jobs can be retried;
- a rebuild occurs when the extractor version changes or the enabled embedding model/dimensions no longer match;
- before a rebuild is saved, the old chunks for that paper are deleted and replaced in one preparation flow.

The current process allows at most two document preparations concurrently per backend process.

This means a 26-page paper may produce multiple parent and child chunks per page during its first preparation, but opening that paper again does not create another copy of those chunks.

## Retrieval and answer generation

### Query routing

Questions are classified into three modes:

- `global`: summaries, overviews, the main contribution, or whole-paper explanations;
- `visual`: questions about figures, tables, charts, diagrams, plots, graphs, or equations;
- `local`: focused questions about a method, result, section, or other detail.

### Global questions

Global questions use ordered parent chunks from across the prepared paper, up to `CHAT_FULL_CONTEXT_MAX_TOKENS`. This route is designed to answer broad requests such as “summarize this paper” without depending on a few keyword matches.

### Local and visual questions

Local retrieval combines:

1. PostgreSQL full-text ranking;
2. PostgreSQL cosine similarity over stored OpenAI embeddings when enabled;
3. Reciprocal Rank Fusion;
4. small section-intent bonuses;
5. parent expansion for the strongest hits;
6. adjacent-child expansion for continuity.

The final evidence packet defaults to ten chunks.

For visual questions, the backend may download the PDF again, render up to three relevant pages in memory, and attach those page images to the OpenAI request. These temporary PDF bytes and images are not persisted.

### Grounded prompting

The OpenAI request contains:

- untrusted paper metadata for identity only;
- a source packet labeled `[S1]`, `[S2]`, and so on;
- up to six recent completed messages for follow-up interpretation only;
- explicit instructions to treat the PDF, metadata, and conversation as untrusted data;
- a requirement that every substantive factual claim cite current source evidence.

Prior assistant replies are never accepted as evidence. Their old source labels are removed before a follow-up request.

### Citation validation

Before a response is displayed and saved, the backend:

- removes source labels outside the current evidence packet;
- normalizes raw LaTeX-like formatting into readable text;
- attempts to repair an uncited block only when it has meaningful lexical overlap with a source;
- removes unsupported blocks;
- maps accepted labels to real stored chunk IDs and page ranges;
- replaces an answer with the insufficient-evidence response if grounding still fails.

The provider response is always buffered until citation and secret-leak checks finish. The browser still receives the validated answer through SSE, but unsafe partial text is not shown first.

### Narrow safety guardrails

- High-confidence credential shapes are redacted from questions, recent history,
  paper metadata, source text, citation excerpts, and generated answers.
- Topic words alone never block a request. The intent check requires an explicit
  operational request together with a severe abuse target.
- Academic and defensive analysis remains allowed. Requests that could enable
  harm are answered at a supported high level without executable steps, while
  only explicit targeted credential theft and sexual abuse of minors are blocked.

## OpenAI provider

The current feature uses OpenAI exclusively.

The backend calls:

- `POST /v1/responses` for chat generation;
- `POST /v1/embeddings` for document and query embeddings.

The current default chat configuration is `gpt-5.6-terra` with `low` reasoning effort and a 1,200-token output limit. Both model and reasoning effort are environment-configurable.

The OpenAI API key is read only by the backend. It must never be placed in frontend JavaScript, committed `.env` files, screenshots, logs, or API responses.

## Persistence and ownership

The additive schema is defined in:

- `backend/migrations/001_chat_with_paper.sql`;
- `backend/migrations/002_hybrid_paper_retrieval.sql`;
- `backend/migrations/003_chat_abuse_controls.sql`;
- `backend/migrations/004_optional_pgvector_search.sql`.

Tables:

- `paper_documents`: one preparation state per paper;
- `paper_chunks`: reusable, paper-scoped extracted evidence and optional embeddings;
- `chat_sessions`: private user-owned conversations;
- `chat_messages`: messages, provider/model details, citations, token usage, latency, and status;
- `chat_usage_daily`: per-user daily request and token totals.

Deleting a session deletes its messages through database cascades. Deleting all chats affects only the authenticated user. Requests for another user's session return `404`.

Extracted paper chunks are shared across users and remain stored until a rebuild, paper deletion, or administrative cleanup. User conversations remain until the user deletes them.

## HTTP interfaces

Public PDF interfaces:

- `GET /papers/{paper_id}`
- `GET /papers/{paper_id}/viewer-url`
- `GET /papers/{paper_id}/pdf`

Authenticated document interfaces:

- `GET /papers/{paper_id}/document-status`
- `POST /papers/{paper_id}/prepare`

Authenticated chat interfaces:

- `POST /chat/sessions`
- `GET /chat/sessions`
- `GET /chat/sessions/{session_id}`
- `PATCH /chat/sessions/{session_id}`
- `DELETE /chat/sessions/{session_id}`
- `DELETE /chat/sessions`
- `GET /chat/sessions/{session_id}/messages`
- `POST /chat/sessions/{session_id}/messages`

The message endpoint returns `text/event-stream` events:

- `message_started`
- `delta`
- `citations`
- `message_completed`
- `error`

## Limits and safety controls

Defaults enforced by the backend:

- 4,000 input characters per message;
- 1,200 output tokens;
- 20 completed requests per user per day;
- 10 chat requests per user per minute and 30 per IP per minute;
- 5 preparation requests per user per day and 20 per IP per day;
- 60 proxied PDF requests per IP per minute;
- a global daily circuit breaker reserving provider request and token units
  before embeddings or generation begin;
- one active generation per session;
- two active generations per user, configurable with
  `CHAT_MAX_CONCURRENT_TURNS_PER_USER`;
- 15 MB maximum PDF size;
- 60-second PDF timeout;
- two concurrent preparations per process;
- idempotency protection through `Idempotency-Key`.

The feature is disabled unless `CHAT_ENABLED=true`. Disabling chat does not remove ordinary paper browsing or external paper links.

## Environment configuration

Required for chat:

```env
DATABASE_URL=postgresql://...
JWT_SECRET=replace-with-a-long-random-secret
JWT_TTL_HOURS=72
CHAT_ENABLED=true
CHAT_DAILY_MESSAGE_LIMIT=20
CHAT_MAX_CONCURRENT_TURNS_PER_USER=2
CHAT_USER_REQUESTS_PER_MINUTE=10
CHAT_IP_REQUESTS_PER_MINUTE=30
CHAT_PREPARES_PER_USER_PER_DAY=5
CHAT_PREPARES_PER_IP_PER_DAY=20
CHAT_PDF_REQUESTS_PER_IP_PER_MINUTE=60
CHAT_GLOBAL_DAILY_PROVIDER_REQUEST_BUDGET=500
CHAT_GLOBAL_DAILY_PROVIDER_TOKEN_BUDGET=2000000
OPENAI_API_KEY=replace-with-server-side-key
ALLOWED_ORIGINS=https://kishormorol.github.io,http://127.0.0.1:8080,http://localhost:8080
```

Recommended current settings:

```env
OPENAI_CHAT_MODEL=gpt-5.6-terra
OPENAI_REASONING_EFFORT=low
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_DIMENSIONS=256
CHAT_EMBEDDINGS_ENABLED=true
```

Optional tuning variables are documented in `.env.example`, including chunk sizes, retrieval candidate counts, visual-page limits, timeouts, PDF hosts, daily quotas, and output limits.

For a local database that should import selected production paper metadata on demand:

```env
PAPER_CATALOG_FALLBACK_URL=https://researchscope-production.up.railway.app
```

## Local development

From the repository root:

```powershell
python -m pip install -r backend/requirements.txt
python scripts/serve_site.py --port 8080
```

In a second terminal:

```powershell
Set-Location backend
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8080/chat-arxiv
```

The backend loads the repository-root `.env`. Keep that file ignored by Git.

## Railway deployment

The feature fits the existing Railway boundary and does not require a vector database or new service.

Deployment requirements:

1. Use the existing PostgreSQL service.
2. Apply migrations `001` through `004` in order, or allow startup
   initialization to create the additive schema and optional vector index.
3. Configure the required backend environment variables.
4. Confirm `/health` reports `db_live: true`, `chat_enabled: true`, and `chat_provider_configured: true`.
5. Add the deployed frontend and intended localhost origins to `ALLOWED_ORIGINS`.
6. Keep the OpenAI key only in Railway environment variables.
7. Configure the ASGI server to trust proxy headers only from Railway's proxy
   boundary, so `request.client` contains the originating client IP used by the
   IP limits. Do not trust arbitrary client-supplied forwarded headers.

Because vectors remain stored as `REAL[]`, standard Railway PostgreSQL is
sufficient and performs cosine ranking in SQL. Railway's pgvector template is
optional; when present, startup enables the extension and creates the HNSW index.
Rate-limit counters and the global circuit breaker are PostgreSQL-backed, so they
remain correct across multiple app replicas. Stale rate-limit windows are cleaned
automatically. Set a limit to `0` only when that specific protection should be
disabled.

## Verification

Relevant test commands:

```powershell
node tests/frontend/chat-paper.test.js
node tests/frontend/chat-arxiv.test.js
python -m pytest tests/test_chat_services.py tests/test_frontend_chat_paper.py tests/test_frontend_chat_arxiv.py -q
```

The tests cover URL normalization, frontend state helpers, extraction/chunking, SSRF allowlisting, provider request construction, retrieval utilities, prompt grounding, citation validation, formatting normalization, and catalog/viewer behavior.

Integration testing must use a disposable PostgreSQL database, not the production Railway database.

## Known limitations

- The discovery search covers papers indexed by ResearchScope; it is not a complete live arXiv.org search.
- Text-inaccessible scanned PDFs are not OCRed.
- Standard PostgreSQL performs exact embedding ranking in SQL. The optional
  pgvector HNSW index accelerates the default 256-dimension configuration.
- Context-preparation percentage is phase-based rather than a backend byte/chunk progress metric.
- Visual questions may require another temporary PDF download.
- Conversation sharing, exports, cross-paper chat, and Highlight & Ask are not implemented.
