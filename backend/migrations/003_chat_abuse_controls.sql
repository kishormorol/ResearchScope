CREATE TABLE IF NOT EXISTS api_rate_limit_windows (
    scope VARCHAR(80) NOT NULL,
    subject_hash VARCHAR(64) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scope, subject_hash, window_start)
);

CREATE INDEX IF NOT EXISTS ix_api_rate_limit_windows_updated
    ON api_rate_limit_windows (updated_at);

CREATE TABLE IF NOT EXISTS chat_global_usage_daily (
    usage_date DATE PRIMARY KEY,
    provider_request_units INTEGER NOT NULL DEFAULT 0,
    provider_token_units BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safe to run periodically or after deployment; current windows are retained.
DELETE FROM api_rate_limit_windows
WHERE updated_at < NOW() - INTERVAL '7 days';
