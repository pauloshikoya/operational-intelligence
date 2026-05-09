-- ingestion/schema.sql

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE raw_data (
    id          BIGSERIAL,
    source      TEXT        NOT NULL,
    domain      TEXT        NOT NULL,
    metric_name TEXT        NOT NULL,
    value       NUMERIC     NOT NULL,
    unit        TEXT,
    raw_json    JSONB,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('raw_data', 'ingested_at');

CREATE TABLE features (
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

SELECT create_hypertable('features', 'computed_at');

CREATE TABLE anomalies (
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

CREATE INDEX ON raw_data (source, ingested_at DESC);
CREATE INDEX ON features (source, metric_name, computed_at DESC);
CREATE INDEX ON anomalies (source, triggered_at DESC);
CREATE INDEX ON anomalies (is_active, anomaly_score DESC);