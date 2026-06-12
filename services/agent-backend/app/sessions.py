"""Postgres-backed session store (asyncpg).

Owns the ``sessions`` table and upserts one row per request. The table is
created on startup (idempotent). Pooled connections via asyncpg.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from .config import Settings

logger = logging.getLogger("agent_backend.sessions")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  uuid PRIMARY KEY,
    app         text        NOT NULL,
    subject     text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_seen   timestamptz NOT NULL DEFAULT now(),
    meta        jsonb       NOT NULL DEFAULT '{}'::jsonb
);
"""

_UPSERT = """
INSERT INTO sessions (session_id, app, subject, created_at, last_seen, meta)
VALUES ($1, $2, $3, now(), now(), $4::jsonb)
ON CONFLICT (session_id) DO UPDATE
    SET last_seen = now(),
        meta = sessions.meta || EXCLUDED.meta
RETURNING session_id;
"""


class SessionStore:
    """Thin async wrapper around an asyncpg connection pool."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Open the connection pool and ensure the sessions table exists."""
        if self._pool is not None:
            return
        s = self._settings
        self._pool = await asyncpg.create_pool(
            host=s.postgres_host,
            port=s.postgres_port,
            user=s.postgres_user,
            password=s.postgres_password,
            database=s.postgres_db,
            min_size=s.postgres_pool_min_size,
            max_size=s.postgres_pool_max_size,
            command_timeout=s.postgres_command_timeout_seconds,
        )
        async with self._acquire() as conn:
            await conn.execute(_CREATE_TABLE)
        logger.info("session store connected", extra={"db": s.postgres_db})

    def _acquire(self):
        """Acquire a pooled connection with a bounded wait."""
        if self._pool is None:
            raise RuntimeError("session store not connected")
        return self._pool.acquire(
            timeout=self._settings.postgres_acquire_timeout_seconds
        )

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> None:
        """Readiness check — raises on failure."""
        async with self._acquire() as conn:
            await conn.execute("SELECT 1")

    async def upsert(
        self,
        session_id: str,
        subject: str,
        app: str,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Insert or refresh a session row and return its id."""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                _UPSERT, session_id, app, subject, json.dumps(meta or {})
            )
        return str(row["session_id"])
