-- Irish Visa Tracker — Starter Schema
-- Run in Supabase SQL Editor

-- Community submissions
CREATE TABLE IF NOT EXISTS community (
    id               SERIAL PRIMARY KEY,
    submitted_at     DATE    NOT NULL DEFAULT CURRENT_DATE,
    irl_series       SMALLINT NOT NULL,
    irl_suffix       SMALLINT NOT NULL,
    embassy          TEXT    NOT NULL,
    visa_type        TEXT    NOT NULL,
    vfs_city         TEXT,
    vfs_date         DATE,
    emb_received     DATE,
    decision_date    DATE,
    outcome          TEXT    NOT NULL DEFAULT 'Pending',
    working_days     SMALLINT,
    calendar_days    SMALLINT,
    vfs_to_emb_days  SMALLINT,
    speed_bracket    TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_community_emb_recv  ON community(emb_received);
CREATE INDEX idx_community_visa_emb  ON community(visa_type, embassy);
CREATE INDEX idx_community_bracket   ON community(speed_bracket);

-- Email alerts
CREATE TABLE IF NOT EXISTS alerts (
    id          SERIAL PRIMARY KEY,
    email       TEXT     NOT NULL,
    irl_series  SMALLINT NOT NULL,
    irl_suffix  SMALLINT NOT NULL,
    embassy     TEXT     NOT NULL,
    registered  DATE     NOT NULL DEFAULT CURRENT_DATE,
    notified    BOOLEAN  NOT NULL DEFAULT FALSE,
    notified_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (email, irl_series, irl_suffix)
);

CREATE INDEX idx_alerts_series  ON alerts(irl_series, irl_suffix);
CREATE INDEX idx_alerts_pending ON alerts(notified) WHERE notified = FALSE;

-- RLS
ALTER TABLE community ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts    ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_community"    ON community FOR SELECT USING (true);
CREATE POLICY "service_insert_community" ON community FOR INSERT WITH CHECK (true);
CREATE POLICY "service_all_alerts"       ON alerts    FOR ALL   USING (true);

-- Date-labelled decisions (seeded from your Excel via seed_supabase.py)
-- Gives the app real decision dates for velocity and cohort analysis.
CREATE TABLE IF NOT EXISTS ods_dates (
    id              SERIAL PRIMARY KEY,
    irl_series      SMALLINT NOT NULL,
    irl_suffix      SMALLINT NOT NULL,
    decision        TEXT     NOT NULL,
    decision_date   DATE     NOT NULL,
    decision_week   TEXT,
    is_baseline     BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = cumulative pre-tracking batch
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (irl_series, irl_suffix)
);

CREATE INDEX idx_ods_dates_series ON ods_dates(irl_series);
CREATE INDEX idx_ods_dates_date   ON ods_dates(decision_date);

ALTER TABLE ods_dates ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public_read_ods_dates"  ON ods_dates FOR SELECT USING (true);
CREATE POLICY "service_insert_ods"     ON ods_dates FOR INSERT WITH CHECK (true);
