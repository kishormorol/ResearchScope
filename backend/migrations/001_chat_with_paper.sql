-- Additive migration for authenticated Chat with Paper.
-- Safe to run after the existing papers/users tables have been created.

CREATE TABLE IF NOT EXISTS paper_documents (
    paper_id TEXT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
    source_url TEXT,
    content_hash TEXT,
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    extractor_version TEXT NOT NULL DEFAULT 'pypdf-v1',
    error_code TEXT,
    prepared_at TIMESTAMPTZ,
    last_accessed_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_chunks (
    id SERIAL PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES paper_documents(paper_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    section TEXT,
    content TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    search_vector TSVECTOR,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_paper_chunks_order UNIQUE (paper_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New chat',
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_message_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'complete',
    provider TEXT,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER,
    client_request_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_chat_message_request UNIQUE (session_id, client_request_id)
);

CREATE TABLE IF NOT EXISTS chat_usage_daily (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, usage_date)
);

CREATE INDEX IF NOT EXISTS ix_paper_documents_status ON paper_documents(status);
CREATE INDEX IF NOT EXISTS ix_paper_chunks_paper_page ON paper_chunks(paper_id, page_start);
CREATE INDEX IF NOT EXISTS ix_paper_chunks_search ON paper_chunks USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_recent ON chat_sessions(user_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_paper_recent ON chat_sessions(user_id, paper_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS ix_chat_messages_session_created ON chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS ix_chat_messages_status ON chat_messages(status);

CREATE OR REPLACE FUNCTION paper_chunks_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', coalesce(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS paper_chunks_search_vector_trigger ON paper_chunks;
CREATE TRIGGER paper_chunks_search_vector_trigger
BEFORE INSERT OR UPDATE OF content ON paper_chunks
FOR EACH ROW EXECUTE FUNCTION paper_chunks_search_vector_update();
