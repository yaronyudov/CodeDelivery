"""Data-access layer for all five DB roles.

Uses psycopg3 with a connection pool.  All methods are synchronous;
the LangGraph runner is single-threaded per node.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _dsn() -> str:
    return (
        f"host={os.getenv('POSTGRES_HOST', 'localhost')} "
        f"port={os.getenv('POSTGRES_PORT', '5432')} "
        f"dbname={os.getenv('POSTGRES_DB', 'build_ship')} "
        f"user={os.getenv('POSTGRES_USER', 'pipeline')} "
        f"password={os.getenv('POSTGRES_PASSWORD', 'pipeline_secret')}"
    )


class PipelineRepo:
    """Thread-safe repository backed by a psycopg3 connection pool."""

    def __init__(self, pool: ConnectionPool | None = None) -> None:
        self._pool = pool or ConnectionPool(conninfo=_dsn(), min_size=1, max_size=5)

    # ------------------------------------------------------------------
    # ROLE 1: Long-term memory
    # ------------------------------------------------------------------
    def save_memory(self, kind: str, key: str, value: dict) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO memory (kind, key, value) VALUES (%s, %s, %s)",
                (kind, key, json.dumps(value)),
            )

    def recall_memory(self, kind: str, key: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT value FROM memory WHERE kind=%s AND key=%s ORDER BY created_at DESC LIMIT 1",
                (kind, key),
            ).fetchone()
            return row[0] if row else None

    # ------------------------------------------------------------------
    # ROLE 2: Artifact cache
    # ------------------------------------------------------------------
    def save_artifact(
        self, run_id: str, kind: str, path: str, version: int, content: str
    ) -> str:
        """Persists content and returns a content_ref UUID."""
        ref = str(uuid.uuid4())
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO artifacts (content_ref, run_id, kind, path, version, content)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (ref, run_id, kind, path, version, content),
            )
        return ref

    def load_artifact(self, content_ref: str) -> str | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT content FROM artifacts WHERE content_ref=%s",
                (content_ref,),
            ).fetchone()
            return row[0] if row else None

    def list_artifacts(self, run_id: str) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT content_ref, kind, path, version FROM artifacts WHERE run_id=%s ORDER BY created_at",
                (run_id,),
                row_factory=dict_row,
            ).fetchall()
            return list(rows)

    # ------------------------------------------------------------------
    # ROLE 3: Shared knowledge base
    # ------------------------------------------------------------------
    def upsert_knowledge(self, run_id: str, topic: str, payload: dict) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO knowledge (run_id, topic, payload, updated_at)
                   VALUES (%s, %s, %s, now())
                   ON CONFLICT (run_id, topic)
                   DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()""",
                (run_id, topic, json.dumps(payload)),
            )

    def get_knowledge(self, run_id: str, topic: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM knowledge WHERE run_id=%s AND topic=%s",
                (run_id, topic),
            ).fetchone()
            return row[0] if row else None

    # ------------------------------------------------------------------
    # ROLE 4: Audit log
    # ------------------------------------------------------------------
    def append_audit(
        self, run_id: str, step: int, agent: str, action: str, decision: dict
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO audit_log (run_id, step, agent, action, decision)
                   VALUES (%s, %s, %s, %s, %s)""",
                (run_id, step, agent, action, json.dumps(decision)),
            )

    def get_audit_log(self, run_id: str) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT step, agent, action, decision, ts FROM audit_log WHERE run_id=%s ORDER BY ts",
                (run_id,),
                row_factory=dict_row,
            ).fetchall()
            return list(rows)

    # ------------------------------------------------------------------
    # ROLE 5: Budget ledger
    # ------------------------------------------------------------------
    def insert_budget_ledger(
        self,
        run_id: str,
        step: int,
        agent: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        est_cost_usd: float,
        allowed: bool,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO budget_ledger
                   (run_id, step, agent, model, tokens_in, tokens_out, est_cost_usd, allowed)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, step, agent, model, tokens_in, tokens_out, est_cost_usd, allowed),
            )

    def reconcile_ledger(self, run_id: str, agent: str, actual_cost_usd: float) -> None:
        """Update the most recent unreconciled ledger row for (run_id, agent)."""
        with self._pool.connection() as conn:
            conn.execute(
                """UPDATE budget_ledger SET actual_cost_usd=%s
                   WHERE id = (
                       SELECT id FROM budget_ledger
                       WHERE run_id=%s AND agent=%s AND actual_cost_usd IS NULL
                       ORDER BY ts DESC LIMIT 1
                   )""",
                (actual_cost_usd, run_id, agent),
            )

    def get_ledger_summary(self, run_id: str) -> dict:
        with self._pool.connection() as conn:
            row = conn.execute(
                """SELECT
                       COUNT(*) AS actions,
                       SUM(tokens_in + tokens_out) AS total_tokens,
                       SUM(COALESCE(actual_cost_usd, est_cost_usd)) AS total_cost_usd
                   FROM budget_ledger WHERE run_id=%s AND allowed=true""",
                (run_id,),
                row_factory=dict_row,
            ).fetchone()
            return dict(row) if row else {}

    # ------------------------------------------------------------------
    # ROLE 6: User auth
    # ------------------------------------------------------------------
    def get_user_by_username(self, username: str) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, is_active FROM users WHERE username=%s",
                (username,),
                row_factory=dict_row,
            ).fetchone()
            return dict(row) if row else None

    def create_user(self, username: str, password_hash: str) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
                (username, password_hash),
            ).fetchone()
            return row[0]  # type: ignore[index]

    # ------------------------------------------------------------------
    # ROLE 7: Run history
    # ------------------------------------------------------------------
    def create_run(
        self,
        run_id: str,
        user_id: int,
        feature_request: str,
        model_config: dict,
        require_approval: bool,
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """INSERT INTO pipeline_runs
                   (run_id, user_id, feature_request, model_config, require_approval)
                   VALUES (%s, %s, %s, %s, %s)""",
                (run_id, user_id, feature_request, json.dumps(model_config), require_approval),
            )

    def finish_run(self, run_id: str, status: str, verdict: str | None = None) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """UPDATE pipeline_runs
                   SET status=%s, verdict=%s, finished_at=now()
                   WHERE run_id=%s""",
                (status, verdict, run_id),
            )

    def list_runs(self, user_id: int, limit: int = 50) -> list[dict]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """SELECT run_id, feature_request, status, verdict, require_approval,
                          created_at, finished_at
                   FROM pipeline_runs
                   WHERE user_id=%s
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (user_id, limit),
                row_factory=dict_row,
            ).fetchall()
            return [dict(r) for r in rows]

    def get_run(self, run_id: str, user_id: int) -> dict | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """SELECT run_id, feature_request, status, verdict, model_config,
                          require_approval, created_at, finished_at
                   FROM pipeline_runs WHERE run_id=%s AND user_id=%s""",
                (run_id, user_id),
                row_factory=dict_row,
            ).fetchone()
            return dict(row) if row else None

    def close(self) -> None:
        self._pool.close()
