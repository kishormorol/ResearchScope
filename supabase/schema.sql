-- ResearchScope — Supabase Schema
-- Run this once in the Supabase SQL Editor (Dashboard → SQL Editor → New query)

-- ── papers ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS papers (
  id                       TEXT PRIMARY KEY,
  canonical_id             TEXT,
  source                   TEXT,
  source_type              TEXT DEFAULT 'preprint',

  -- bibliographic
  title                    TEXT,
  abstract                 TEXT,
  authors                  JSONB DEFAULT '[]',
  author_ids               JSONB DEFAULT '[]',
  affiliations_raw         JSONB DEFAULT '[]',
  lab_ids                  JSONB DEFAULT '[]',
  university_ids           JSONB DEFAULT '[]',
  year                     INTEGER,
  published_date           TEXT,
  venue                    TEXT,
  conference_rank          TEXT DEFAULT '',
  paper_url                TEXT DEFAULT '',
  pdf_url                  TEXT DEFAULT '',
  citations                INTEGER DEFAULT 0,

  -- topics / tags
  topics                   JSONB DEFAULT '[]',
  tags                     JSONB DEFAULT '[]',
  cluster_id               TEXT DEFAULT '',

  -- classification
  paper_type               TEXT DEFAULT '',
  difficulty_level         TEXT DEFAULT 'L2',
  difficulty_reason        TEXT DEFAULT '',
  prerequisites            JSONB DEFAULT '[]',
  maturity_stage           TEXT DEFAULT 'emerging',

  -- scores
  paper_score              FLOAT DEFAULT 0.0,
  read_first_score         FLOAT DEFAULT 0.0,
  content_potential_score  FLOAT DEFAULT 0.0,
  interestingness_score    FLOAT DEFAULT 0.0,
  hype_score               FLOAT DEFAULT 0.0,
  evidence_strength        FLOAT DEFAULT 0.0,
  score_breakdown          JSONB DEFAULT '{}',

  -- content fields
  summary                  TEXT DEFAULT '',
  key_contribution         TEXT DEFAULT '',
  why_it_matters           TEXT DEFAULT '',
  content_hook             TEXT DEFAULT '',
  plain_english_explanation TEXT DEFAULT '',
  technical_summary        TEXT DEFAULT '',
  limitations              JSONB DEFAULT '[]',
  future_work              JSONB DEFAULT '[]',
  research_gap_signals     JSONB DEFAULT '[]',

  -- creator outputs
  tweet_thread             TEXT DEFAULT '',
  linkedin_post            TEXT DEFAULT '',
  newsletter_blurb         TEXT DEFAULT '',
  video_script_outline     TEXT DEFAULT '',
  one_line_takeaway        TEXT DEFAULT '',
  biggest_caveat           TEXT DEFAULT '',
  read_this_if             TEXT DEFAULT '',

  -- metadata
  fetched_at               TEXT,
  created_at               TIMESTAMPTZ DEFAULT NOW(),
  updated_at               TIMESTAMPTZ DEFAULT NOW()
);

-- indexes for common queries
CREATE INDEX IF NOT EXISTS papers_venue_idx         ON papers(venue);
CREATE INDEX IF NOT EXISTS papers_year_idx          ON papers(year);
CREATE INDEX IF NOT EXISTS papers_score_idx         ON papers(paper_score DESC);
CREATE INDEX IF NOT EXISTS papers_source_type_idx   ON papers(source_type);
CREATE INDEX IF NOT EXISTS papers_published_date_idx ON papers(published_date DESC);
CREATE INDEX IF NOT EXISTS papers_canonical_id_idx  ON papers(canonical_id);

-- auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER papers_updated_at
  BEFORE UPDATE ON papers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── authors ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS authors (
  author_id         TEXT PRIMARY KEY,
  name              TEXT,
  aliases           JSONB DEFAULT '[]',
  affiliations      JSONB DEFAULT '[]',
  paper_ids         JSONB DEFAULT '[]',
  recent_paper_ids  JSONB DEFAULT '[]',
  topics            JSONB DEFAULT '[]',
  avg_paper_score   FLOAT DEFAULT 0.0,
  momentum_score    FLOAT DEFAULT 0.0,
  momentum_breakdown JSONB DEFAULT '{}',
  conference_counts JSONB DEFAULT '{}',
  lab_ids           JSONB DEFAULT '[]',
  university_ids    JSONB DEFAULT '[]',
  summary_profile   TEXT DEFAULT '',
  h_index           INTEGER DEFAULT 0,
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS authors_momentum_idx ON authors(momentum_score DESC);

-- ── topics ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS topics (
  id                TEXT PRIMARY KEY,
  name              TEXT,
  keywords          JSONB DEFAULT '[]',
  paper_ids         JSONB DEFAULT '[]',
  trend_score       FLOAT DEFAULT 0.0,
  gap_summary       TEXT DEFAULT '',
  starter_pack_ids  JSONB DEFAULT '[]',
  frontier_pack_ids JSONB DEFAULT '[]',
  difficulty        TEXT DEFAULT 'intermediate',
  prerequisites     JSONB DEFAULT '[]',
  related_topics    JSONB DEFAULT '[]',
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ── gaps ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gaps (
  gap_id              TEXT PRIMARY KEY,
  topic               TEXT,
  title               TEXT,
  description         TEXT,
  evidence_paper_ids  JSONB DEFAULT '[]',
  gap_type            TEXT DEFAULT 'explicit',
  confidence          FLOAT DEFAULT 0.5,
  starter_idea        TEXT DEFAULT '',
  frequency           INTEGER DEFAULT 1,
  suggested_projects  JSONB DEFAULT '[]',
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── labs ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS labs (
  lab_id          TEXT PRIMARY KEY,
  name            TEXT,
  aliases         JSONB DEFAULT '[]',
  university      TEXT DEFAULT '',
  authors         JSONB DEFAULT '[]',
  paper_ids       JSONB DEFAULT '[]',
  recent_papers   JSONB DEFAULT '[]',
  topics          JSONB DEFAULT '[]',
  avg_paper_score FLOAT DEFAULT 0.0,
  momentum_score  FLOAT DEFAULT 0.0,
  a_star_output   INTEGER DEFAULT 0,
  summary_profile TEXT DEFAULT '',
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Enable public read access (anon key can SELECT, only service role can write) ──
ALTER TABLE papers  ENABLE ROW LEVEL SECURITY;
ALTER TABLE authors ENABLE ROW LEVEL SECURITY;
ALTER TABLE topics  ENABLE ROW LEVEL SECURITY;
ALTER TABLE gaps    ENABLE ROW LEVEL SECURITY;
ALTER TABLE labs    ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read papers"  ON papers  FOR SELECT USING (true);
CREATE POLICY "public read authors" ON authors FOR SELECT USING (true);
CREATE POLICY "public read topics"  ON topics  FOR SELECT USING (true);
CREATE POLICY "public read gaps"    ON gaps    FOR SELECT USING (true);
CREATE POLICY "public read labs"    ON labs    FOR SELECT USING (true);
