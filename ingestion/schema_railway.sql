-- schema_railway.sql
-- Plain Postgres version for Railway deployment (no TimescaleDB)

CREATE TABLE IF NOT EXISTS raw_data (
    id          BIGSERIAL,
    source      TEXT        NOT NULL,
    domain      TEXT        NOT NULL,
    metric_name TEXT        NOT NULL,
    value       NUMERIC     NOT NULL,
    unit        TEXT,
    raw_json    JSONB,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS features (
    id              BIGSERIAL,
    source          TEXT        NOT NULL,
    metric_name     TEXT        NOT NULL,
    value_raw       NUMERIC     NOT NULL,
    value_7d_avg    NUMERIC,
    value_7d_stddev NUMERIC,
    z_score         NUMERIC,
    pct_change_1d   NUMERIC,
    pct_change_7d   NUMERIC,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS anomalies (
    id                  BIGSERIAL PRIMARY KEY,
    source              TEXT        NOT NULL,
    metric_name         TEXT        NOT NULL,
    anomaly_score       NUMERIC     NOT NULL,
    severity            TEXT        DEFAULT 'medium',
    z_score_contrib     NUMERIC,
    cusum_contrib       NUMERIC,
    iforest_contrib     NUMERIC,
    narrative           TEXT,
    narrative_json      JSONB,
    triggered_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    is_active           BOOLEAN     DEFAULT TRUE,
    suppressed          BOOLEAN     DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS raw_data_source_idx
    ON raw_data (source, ingested_at DESC);

CREATE INDEX IF NOT EXISTS features_source_idx
    ON features (source, metric_name, computed_at DESC);

CREATE INDEX IF NOT EXISTS anomalies_source_idx
    ON anomalies (source, triggered_at DESC);

CREATE INDEX IF NOT EXISTS anomalies_score_idx
    ON anomalies (is_active, anomaly_score DESC);