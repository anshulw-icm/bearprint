-- ============================================================
-- Bearprint — Supabase SQL Schema
-- Run this in: Supabase Dashboard → SQL Editor → New query
-- ============================================================


-- ── TABLE 1: bearprint_daily ─────────────────────────────────
-- One row per trading day. Written by compute.py daily.

CREATE TABLE IF NOT EXISTS bearprint_daily (
    id         BIGSERIAL PRIMARY KEY,
    date       DATE        NOT NULL UNIQUE,  -- trading date, e.g. 2024-11-05
    bp_value   NUMERIC(5,2) NOT NULL,        -- 0.00 to 100.00
    losers     INTEGER      NOT NULL,         -- stocks that closed below prev close
    total      INTEGER      NOT NULL,         -- total stocks in universe
    zone       TEXT         NOT NULL          -- 'calm' | 'caution' | 'crash'
                CHECK (zone IN ('calm', 'caution', 'crash')),
    avg_7d     NUMERIC(5,2) NOT NULL DEFAULT 0, -- rolling 7-day average
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Index for fast date-range queries (history endpoint)
CREATE INDEX IF NOT EXISTS idx_bearprint_daily_date
    ON bearprint_daily (date DESC);

-- ── TABLE 2: feedback ────────────────────────────────────────
-- User responses from the feedback form at the bottom of the webapp.

CREATE TABLE IF NOT EXISTS feedback (
    id          BIGSERIAL    PRIMARY KEY,
    q1          TEXT,        -- "yes" | "maybe" | "no"
    q2          TEXT,        -- "hedge" | "hold" | "sell" | "nothing"
    q3          TEXT,        -- free-text response (optional)
    bp_at_time  NUMERIC(5,2),-- Bearprint value when feedback was submitted
    user_agent  TEXT,        -- browser UA for basic deduplication
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── ROW LEVEL SECURITY ────────────────────────────────────────
-- Enable RLS so only your service role key can write,
-- but anon key can read bearprint_daily (public data).

ALTER TABLE bearprint_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback         ENABLE ROW LEVEL SECURITY;

-- Public can read Bearprint history (needed by frontend)
CREATE POLICY "Public read bearprint_daily"
    ON bearprint_daily FOR SELECT
    USING (true);

-- Only service role (your compute.py) can insert/update
CREATE POLICY "Service insert bearprint_daily"
    ON bearprint_daily FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Service update bearprint_daily"
    ON bearprint_daily FOR UPDATE
    USING (true);

-- Anyone can submit feedback (anon insert)
CREATE POLICY "Public insert feedback"
    ON feedback FOR INSERT
    WITH CHECK (true);

-- Only service role can read feedback responses
CREATE POLICY "Service read feedback"
    ON feedback FOR SELECT
    USING (auth.role() = 'service_role');


-- ── SEED: 30 days of sample data (optional, for testing) ─────
-- Remove this block once compute.py is running live.

INSERT INTO bearprint_daily (date, bp_value, losers, total, zone, avg_7d) VALUES
  (CURRENT_DATE - 29, 24.4, 122, 500, 'calm',    24.4),
  (CURRENT_DATE - 28, 31.2, 156, 500, 'calm',    27.8),
  (CURRENT_DATE - 27, 28.0, 140, 500, 'calm',    27.9),
  (CURRENT_DATE - 26, 35.6, 178, 500, 'calm',    29.8),
  (CURRENT_DATE - 25, 22.8, 114, 500, 'calm',    28.4),
  (CURRENT_DATE - 24, 41.0, 205, 500, 'calm',    30.5),
  (CURRENT_DATE - 23, 38.4, 192, 500, 'calm',    31.6),
  (CURRENT_DATE - 22, 67.2, 336, 500, 'crash',   36.9),
  (CURRENT_DATE - 21, 72.8, 364, 500, 'crash',   43.9),
  (CURRENT_DATE - 20, 71.0, 355, 500, 'crash',   46.8),
  (CURRENT_DATE - 19, 68.4, 342, 500, 'crash',   52.7),
  (CURRENT_DATE - 18, 74.2, 371, 500, 'crash',   57.6),
  (CURRENT_DATE - 17, 65.6, 328, 500, 'crash',   62.7),
  (CURRENT_DATE - 16, 58.8, 294, 500, 'caution', 65.4),
  (CURRENT_DATE - 15, 44.2, 221, 500, 'calm',    64.9),
  (CURRENT_DATE - 14, 38.6, 193, 500, 'calm',    60.4),
  (CURRENT_DATE - 13, 32.0, 160, 500, 'calm',    56.9),
  (CURRENT_DATE - 12, 29.4, 147, 500, 'calm',    48.9),
  (CURRENT_DATE - 11, 27.2, 136, 500, 'calm',    42.3),
  (CURRENT_DATE - 10, 33.8, 169, 500, 'calm',    37.7),
  (CURRENT_DATE -  9, 19.6, 98,  500, 'calm',    32.1),
  (CURRENT_DATE -  8, 22.4, 112, 500, 'calm',    29.5),
  (CURRENT_DATE -  7, 47.0, 235, 500, 'caution', 30.2),
  (CURRENT_DATE -  6, 53.6, 268, 500, 'caution', 33.3),
  (CURRENT_DATE -  5, 61.2, 306, 500, 'caution', 38.2),
  (CURRENT_DATE -  4, 58.4, 292, 500, 'caution', 45.1),
  (CURRENT_DATE -  3, 63.8, 319, 500, 'caution', 47.1),
  (CURRENT_DATE -  2, 55.2, 276, 500, 'caution', 51.6),
  (CURRENT_DATE -  1, 49.6, 248, 500, 'caution', 52.5),
  (CURRENT_DATE,      52.4, 262, 500, 'caution', 56.3)
ON CONFLICT (date) DO NOTHING;
