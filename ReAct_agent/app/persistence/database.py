"""PostgreSQL connection and schema bootstrap for durable ReAct execution.

Uses the same DATABASE_URL / FINZER_ENV_FILE conventions as the wishlist
repository. Connections are opened per operation and owned by the caller.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = Path(os.getenv("FINZER_ENV_FILE", str(PROJECT_ROOT / "local.env")))
if ENV_FILE.is_file():
    load_dotenv(ENV_FILE, override=False)
else:
    load_dotenv(override=False)


class PersistenceError(Exception):
    """Base exception for persistence infrastructure failures."""


class PersistenceConfigurationError(PersistenceError):
    """Raised when the PostgreSQL connection string is unavailable."""


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise PersistenceConfigurationError(
            "DATABASE_URL is not configured. Set it in the environment or local.env."
        )
    return url


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Yield a connection; commit on success and roll back on failure.

    A fresh connection is used for each unit of work. Never share it across
    concurrent runs or store it on the graph instance.
    """
    with psycopg.connect(get_database_url(), row_factory=dict_row) as conn:
        yield conn


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    user_id TEXT,
    state JSONB NOT NULL,
    execution_status TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status
    ON agent_runs (execution_status);

CREATE TABLE IF NOT EXISTS agent_checkpoints (
    checkpoint_id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    state JSONB NOT NULL,
    step_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_checkpoints_run
    ON agent_checkpoints (run_id, checkpoint_id DESC);

CREATE TABLE IF NOT EXISTS agent_approval_requests (
    request_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_approvals_run
    ON agent_approval_requests (run_id);

CREATE TABLE IF NOT EXISTS agent_audit_events (
    event_id BIGSERIAL PRIMARY KEY,
    run_id TEXT,
    user_id TEXT,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_audit_run
    ON agent_audit_events (run_id, event_id);

CREATE TABLE IF NOT EXISTS agent_tool_executions (
    run_id TEXT NOT NULL,
    call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    approval_request_id TEXT,
    status TEXT NOT NULL,
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, call_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_tool_approval_consumption
    ON agent_tool_executions (approval_request_id)
    WHERE approval_request_id IS NOT NULL;
"""


def initialize_schema() -> None:
    """Create Phase 6 tables and indexes, without dropping existing data.

    Intended for initial local setup. Production deployments should use
    versioned migrations and restricted database roles instead.
    """
    with get_connection() as conn:
        conn.execute(_SCHEMA_SQL)
