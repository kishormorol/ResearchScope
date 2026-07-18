-- Optional zero-data-loss acceleration for the default 256-dimension embeddings.
-- Standard Railway PostgreSQL does not ship pgvector, so REAL[] remains the
-- source column and PostgreSQL array cosine search remains the compatible path.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_available_extensions WHERE name = 'vector'
    ) THEN
        EXECUTE 'CREATE EXTENSION IF NOT EXISTS vector';
        EXECUTE $index$
            CREATE INDEX IF NOT EXISTS ix_paper_chunks_embedding_hnsw_256
            ON paper_chunks USING hnsw (
                (embedding::vector(256)) vector_cosine_ops
            )
            WHERE embedding IS NOT NULL
              AND array_length(embedding, 1) = 256
        $index$;
    END IF;
END
$$;
