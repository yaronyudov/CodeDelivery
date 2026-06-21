-- Build & Ship Pipeline — Postgres schema
-- Run once: psql $DATABASE_URL -f schema.sql

-- ROLE 1: long-term memory ---------------------------------------------------
CREATE TABLE IF NOT EXISTS memory (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT        NOT NULL,   -- 'pattern', 'past_plan', 'lesson'
    key         TEXT        NOT NULL,
    value       JSONB       NOT NULL,
    -- embedding VECTOR(1536),          -- uncomment when pgvector is available
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS memory_kind_key ON memory (kind, key);

-- ROLE 2: artifact cache (keeps PipelineState small via content_ref) ----------
CREATE TABLE IF NOT EXISTS artifacts (
    content_ref TEXT        PRIMARY KEY,   -- referenced from PipelineState
    run_id      TEXT        NOT NULL,
    kind        TEXT        NOT NULL,
    path        TEXT        NOT NULL,
    version     INT         NOT NULL,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS artifacts_run_id ON artifacts (run_id);

-- ROLE 3: shared knowledge base (all review agents read the same context) -----
CREATE TABLE IF NOT EXISTS knowledge (
    id          BIGSERIAL   PRIMARY KEY,
    run_id      TEXT        NOT NULL,
    topic       TEXT        NOT NULL,   -- 'codebase_map', 'known_cves', ...
    payload     JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS knowledge_run_topic ON knowledge (run_id, topic);

-- ROLE 4: audit log (every agent decision, timestamped) ----------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    run_id      TEXT        NOT NULL,
    step        INT         NOT NULL,
    agent       TEXT        NOT NULL,
    action      TEXT        NOT NULL,
    decision    JSONB       NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_log_run_step ON audit_log (run_id, step);

-- ROLE 5: budget ledger (one row per model action, pre- and post-flight) ------
CREATE TABLE IF NOT EXISTS budget_ledger (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          TEXT            NOT NULL,
    step            INT             NOT NULL,
    agent           TEXT            NOT NULL,
    model           TEXT            NOT NULL,
    tokens_in       INT             NOT NULL,
    tokens_out      INT             NOT NULL,
    est_cost_usd    NUMERIC(10, 6)  NOT NULL,   -- pre-flight estimate
    actual_cost_usd NUMERIC(10, 6),             -- reconciled after the call
    allowed         BOOLEAN         NOT NULL,   -- did the guard permit it?
    ts              TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS budget_ledger_run_id ON budget_ledger (run_id);
