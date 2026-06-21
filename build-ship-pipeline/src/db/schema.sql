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

-- ROLE 6: auth — pre-seeded users, no self-registration ----------------------
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL   PRIMARY KEY,
    username      TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,   -- bcrypt cost=12, never plaintext
    is_active     BOOLEAN     NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ROLE 7: run history — one row per pipeline execution -----------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id           TEXT        PRIMARY KEY,
    user_id          BIGINT      NOT NULL REFERENCES users(id),
    feature_request  TEXT        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'running',  -- running|done|halted|stopped
    model_config     JSONB,
    require_approval BOOLEAN     NOT NULL DEFAULT false,
    verdict          TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS pipeline_runs_user ON pipeline_runs (user_id, created_at DESC);

-- ROLE 8: skill definitions — prompt injections and agent toggles -------------
CREATE TABLE IF NOT EXISTS skills (
    id            TEXT        PRIMARY KEY,   -- slug: "typescript", "skip-docker"
    name          TEXT        NOT NULL,
    description   TEXT        NOT NULL DEFAULT '',
    kind          TEXT        NOT NULL
                              CHECK (kind IN ('prompt_injection', 'agent_toggle')),
    target_agents TEXT[]      NOT NULL DEFAULT '{}',  -- empty = all agents
    prompt_addon  TEXT,                               -- injected text (prompt_injection)
    is_default    BOOLEAN     NOT NULL DEFAULT false,
    is_system     BOOLEAN     NOT NULL DEFAULT false, -- built-in, not deletable
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS skills_kind ON skills (kind);
CREATE INDEX IF NOT EXISTS skills_default ON skills (is_default) WHERE is_default = true;

-- ROLE 9: per-run skill overrides — add/remove skills from session defaults ---
CREATE TABLE IF NOT EXISTS run_skill_overrides (
    run_id      TEXT NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    agent_name  TEXT NOT NULL,   -- specific agent name OR '*' for all agents
    skill_id    TEXT NOT NULL REFERENCES skills(id),
    action      TEXT NOT NULL CHECK (action IN ('add', 'remove')),
    PRIMARY KEY (run_id, agent_name, skill_id)
);

-- ROLE 10: RAG document store —————————————————————————————————————————————————
-- Chunked text corpus used by all retrieval strategies.
-- Populated by indexer.py at run start (artifacts) or on demand (memory, knowledge).
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- trigram similarity (BM25 fallback)
-- Uncomment next line after running: CREATE EXTENSION vector;
-- CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    id          BIGSERIAL   PRIMARY KEY,
    corpus      TEXT        NOT NULL,       -- 'memory' | 'knowledge' | 'artifacts' | 'custom'
    doc_id      TEXT        NOT NULL,       -- stable identifier for the source document
    chunk_index INT         NOT NULL DEFAULT 0,
    content     TEXT        NOT NULL,
    metadata    JSONB       NOT NULL DEFAULT '{}',
    -- embedding VECTOR(1536),             -- enable once pgvector extension is loaded
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS rag_documents_doc_chunk ON rag_documents (doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS rag_documents_corpus ON rag_documents (corpus);
-- GIN index enables Postgres full-text search (free BM25-equivalent)
CREATE INDEX IF NOT EXISTS rag_documents_fts
    ON rag_documents USING GIN(to_tsvector('english', content));

-- ROLE 11: RAG entity graph — nodes ——————————————————————————————————————————
CREATE TABLE IF NOT EXISTS rag_entities (
    id          BIGSERIAL   PRIMARY KEY,
    corpus      TEXT        NOT NULL,
    run_id      TEXT,                       -- null = global entity
    name        TEXT        NOT NULL,
    type        TEXT        NOT NULL,       -- 'file'|'function'|'class'|'service'|'concept'|'technology'
    description TEXT        NOT NULL DEFAULT '',
    attributes  JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_entities_corpus_run ON rag_entities (corpus, run_id);
CREATE INDEX IF NOT EXISTS rag_entities_name       ON rag_entities (name text_pattern_ops);
-- Dedup key so graph indexing can upsert entities (ON CONFLICT target)
CREATE UNIQUE INDEX IF NOT EXISTS rag_entities_corpus_name ON rag_entities (corpus, name);

-- ROLE 12: RAG entity graph — edges ——————————————————————————————————————————
CREATE TABLE IF NOT EXISTS rag_relations (
    id          BIGSERIAL   PRIMARY KEY,
    source_id   BIGINT      NOT NULL REFERENCES rag_entities(id) ON DELETE CASCADE,
    target_id   BIGINT      NOT NULL REFERENCES rag_entities(id) ON DELETE CASCADE,
    relation    TEXT        NOT NULL,       -- 'imports'|'calls'|'inherits'|'uses'|'defines'|'depends_on'
    weight      FLOAT       NOT NULL DEFAULT 1.0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_relations_source ON rag_relations (source_id);
CREATE INDEX IF NOT EXISTS rag_relations_target ON rag_relations (target_id);

