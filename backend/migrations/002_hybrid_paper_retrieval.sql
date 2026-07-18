-- Additive migration for Railway-friendly hybrid paper retrieval.
-- Embeddings are stored as standard PostgreSQL REAL arrays so this migration
-- does not require pgvector or a different Railway Postgres image.

ALTER TABLE paper_documents
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER NOT NULL DEFAULT 0;

ALTER TABLE paper_chunks
    ADD COLUMN IF NOT EXISTS token_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS parent_chunk_index INTEGER,
    ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'paragraph',
    ADD COLUMN IF NOT EXISTS embedding REAL[],
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS bounding_box JSONB;

CREATE INDEX IF NOT EXISTS ix_paper_chunks_parent
    ON paper_chunks (paper_id, parent_chunk_index);

CREATE INDEX IF NOT EXISTS ix_paper_chunks_type
    ON paper_chunks (paper_id, content_type);
