"""
Neon PostgreSQL client — REST API and direct connection support.
Uses NEON_REST_API for HTTP queries (no psycopg2 required).
"""
import os
import urllib.request
import json
import logging

log = logging.getLogger("neon_client")

_REST_API = os.getenv("NEON_REST_API", "")
_DB_URL = os.getenv("NEON_DB_URL", "")
_PROJECT = os.getenv("NEON_PROJECT_ID", "")


def _rest_headers() -> dict:
    return {"Content-Type": "application/json", "Accept": "application/json"}


def query(sql: str, params: list | None = None) -> dict:
    """Execute SQL via Neon REST API."""
    if not _REST_API:
        raise ValueError("NEON_REST_API not set")
    body = json.dumps({"sql": sql, "params": params or []}).encode()
    req = urllib.request.Request(
        f"{_REST_API}/query",
        data=body,
        headers=_rest_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as exc:
        log.error("neon query failed: %s | sql: %s", exc, sql[:100])
        raise


def execute(sql: str, params: list | None = None) -> dict:
    """Run a DML statement (INSERT/UPDATE/DELETE)."""
    return query(sql, params)


def get_connection_string() -> str:
    return _DB_URL


def health_check() -> bool:
    try:
        result = query("SELECT 1 AS alive")
        return bool(result.get("rows"))
    except Exception:
        return False


def create_tables_if_missing() -> None:
    """Ensure FractalMesh schema exists in Neon (mirrors Supabase schema)."""
    ddl_statements = [
        """CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            title TEXT, url TEXT, summary TEXT,
            source TEXT, intent_score REAL DEFAULT 0,
            tier TEXT DEFAULT 'basic',
            tags TEXT[] DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS revenue (
            id SERIAL PRIMARY KEY,
            source TEXT, amount REAL, currency TEXT DEFAULT 'AUD',
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS agent_log (
            id SERIAL PRIMARY KEY,
            agent TEXT, task TEXT, success BOOLEAN,
            value_generated REAL DEFAULT 0,
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
    ]
    for ddl in ddl_statements:
        try:
            execute(ddl)
        except Exception as exc:
            log.warning("neon create_tables: %s", exc)
