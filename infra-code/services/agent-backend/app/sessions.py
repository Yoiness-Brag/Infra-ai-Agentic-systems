"""Postgres-backed relational state (asyncpg).

Owns the ``sessions`` table plus the ``documents`` / ``document_jobs`` ledger
that backs PDF ingestion. Schema is created by the Postgres init ConfigMap; the
statements here are DML only, so the runtime role needs no DDL privilege.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from .config import Settings
from .resilience import Breaker, CircuitOpenError

logger = logging.getLogger("agent_backend.sessions")


class SessionOwnershipError(PermissionError):
    """A caller supplied a session id owned by a different subject."""


_UPSERT = """
INSERT INTO sessions (session_id, app, subject, created_at, last_seen, meta)
VALUES ($1, $2, $3, now(), now(), $4::jsonb)
ON CONFLICT (session_id) DO UPDATE
    SET last_seen = now(),
        meta = sessions.meta || EXCLUDED.meta
    WHERE sessions.subject = EXCLUDED.subject
      AND sessions.app = EXCLUDED.app
RETURNING session_id;
"""

_INSERT_DOCUMENT = """
INSERT INTO documents (document_id, app, owner_subject, filename, content_sha256,
                       bytes, page_count, object_key, group_id)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (app, owner_subject, content_sha256) DO NOTHING
RETURNING document_id;
"""

_SELECT_DOCUMENT_BY_HASH = """
SELECT document_id, filename, bytes, page_count, object_key, group_id, created_at
FROM documents
WHERE app = $1 AND owner_subject = $2 AND content_sha256 = $3;
"""

_SELECT_DOCUMENT = """
SELECT d.document_id, d.filename, d.bytes, d.page_count, d.object_key,
       d.group_id, d.created_at,
       j.job_id, j.state, j.chunks_total, j.chunks_done, j.error
FROM documents d
LEFT JOIN document_jobs j ON j.document_id = d.document_id
WHERE d.app = $1 AND d.owner_subject = $2 AND d.document_id = $3;
"""

_LIST_DOCUMENTS = """
SELECT d.document_id, d.filename, d.bytes, d.page_count, d.created_at,
       j.state, j.chunks_total, j.chunks_done
FROM documents d
LEFT JOIN document_jobs j ON j.document_id = d.document_id
WHERE d.app = $1 AND d.owner_subject = $2
ORDER BY d.created_at DESC
LIMIT $3 OFFSET $4;
"""

_DELETE_DOCUMENT = """
DELETE FROM documents
WHERE app = $1 AND owner_subject = $2 AND document_id = $3
RETURNING object_key, group_id;
"""

_SELECT_DOCUMENT_FOR_JOB = """
SELECT document_id, filename, object_key, group_id, page_count
FROM documents
WHERE document_id = $1;
"""

_INSERT_JOB = """
INSERT INTO document_jobs (job_id, document_id, state)
VALUES ($1, $2, 'queued')
RETURNING job_id;
"""

_CLAIM_JOB = """
WITH claimed AS (
    SELECT job_id
    FROM document_jobs
    WHERE state = 'queued' AND attempts < $1
    ORDER BY updated_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE document_jobs j
SET state = 'running',
    attempts = j.attempts + 1,
    claimed_at = now(),
    updated_at = now()
FROM claimed
WHERE j.job_id = claimed.job_id
RETURNING j.job_id, j.document_id, j.attempts;
"""

_FINISH_JOB = """
UPDATE document_jobs
SET state = $2, chunks_total = $3, chunks_done = $4, error = $5, updated_at = now()
WHERE job_id = $1;
"""

_REQUEUE_JOB = """
UPDATE document_jobs
SET state = CASE WHEN attempts >= $2 THEN 'failed' ELSE 'queued' END,
    error = $3,
    updated_at = now()
WHERE job_id = $1
RETURNING state;
"""

_PROGRESS_JOB = """
UPDATE document_jobs
SET chunks_total = $2, chunks_done = $3, updated_at = now()
WHERE job_id = $1;
"""


class SessionStore:
    """Async wrapper around an asyncpg pool, guarded by a circuit breaker."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool: asyncpg.Pool | None = None
        self._breaker = Breaker(name="postgres", threshold=5, cooldown=15.0)

    async def connect(self) -> None:
        """Open the connection pool."""
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
        logger.info("session store connected", extra={"db": s.postgres_db})

    @property
    def connected(self) -> bool:
        """True once the pool is open."""
        return self._pool is not None

    def _acquire(self):
        """Acquire a pooled connection with a bounded wait."""
        if self._pool is None:
            raise RuntimeError("session store not connected")
        if not self._breaker.allow():
            raise CircuitOpenError("postgres circuit breaker is open")
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
        self._breaker.record_success()

    async def upsert(
        self,
        session_id: str,
        subject: str,
        app: str,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """Insert or refresh a session row.

        The ``ON CONFLICT`` carries a subject+app predicate, so a caller that
        supplies another subject's session id updates zero rows and is rejected
        rather than silently taking over that session's memory partition.
        """
        try:
            async with self._acquire() as conn:
                row = await conn.fetchrow(
                    _UPSERT, session_id, app, subject, json.dumps(meta or {})
                )
        except CircuitOpenError:
            raise
        except Exception:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        if row is None:
            raise SessionOwnershipError("session_id belongs to a different subject")
        return str(row["session_id"])

    async def find_document_by_hash(
        self, app: str, subject: str, sha256: str
    ) -> asyncpg.Record | None:
        """Return an existing document row for this owner and content hash."""
        async with self._acquire() as conn:
            return await conn.fetchrow(_SELECT_DOCUMENT_BY_HASH, app, subject, sha256)

    async def create_document(self, **kw: Any) -> str | None:
        """Insert a document row. Returns None when the content already exists."""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                _INSERT_DOCUMENT,
                kw["document_id"],
                kw["app"],
                kw["owner_subject"],
                kw["filename"],
                kw["content_sha256"],
                kw["bytes"],
                kw["page_count"],
                kw["object_key"],
                kw["group_id"],
            )
        return str(row["document_id"]) if row else None

    async def create_job(self, job_id: str, document_id: str) -> str:
        """Queue an ingestion job for a document."""
        async with self._acquire() as conn:
            row = await conn.fetchrow(_INSERT_JOB, job_id, document_id)
        return str(row["job_id"])

    async def get_document_for_job(self, document_id: str) -> asyncpg.Record | None:
        """Fetch the fields the ingest worker needs, without an owner scope."""
        async with self._acquire() as conn:
            return await conn.fetchrow(_SELECT_DOCUMENT_FOR_JOB, document_id)

    async def claim_job(self, max_attempts: int) -> asyncpg.Record | None:
        """Atomically claim one queued job (SKIP LOCKED)."""
        async with self._acquire() as conn:
            return await conn.fetchrow(_CLAIM_JOB, max_attempts)

    async def job_progress(self, job_id: str, total: int, done: int) -> None:
        """Record incremental ingestion progress."""
        async with self._acquire() as conn:
            await conn.execute(_PROGRESS_JOB, job_id, total, done)

    async def finish_job(
        self, job_id: str, state: str, total: int, done: int, error: str | None
    ) -> None:
        """Mark a job terminal."""
        async with self._acquire() as conn:
            await conn.execute(_FINISH_JOB, job_id, state, total, done, error)

    async def requeue_job(self, job_id: str, max_attempts: int, error: str) -> str:
        """Return a failed job to the queue, or fail it once attempts run out."""
        async with self._acquire() as conn:
            row = await conn.fetchrow(_REQUEUE_JOB, job_id, max_attempts, error)
        return str(row["state"]) if row else "unknown"

    async def get_document(
        self, app: str, subject: str, document_id: str
    ) -> asyncpg.Record | None:
        """Fetch one document plus its job state, scoped to its owner."""
        async with self._acquire() as conn:
            return await conn.fetchrow(_SELECT_DOCUMENT, app, subject, document_id)

    async def list_documents(
        self, app: str, subject: str, limit: int, offset: int
    ) -> list[asyncpg.Record]:
        """List this subject's documents, newest first."""
        async with self._acquire() as conn:
            return list(await conn.fetch(_LIST_DOCUMENTS, app, subject, limit, offset))

    async def delete_document(
        self, app: str, subject: str, document_id: str
    ) -> asyncpg.Record | None:
        """Delete a document row and return its object key + graph partition."""
        async with self._acquire() as conn:
            return await conn.fetchrow(_DELETE_DOCUMENT, app, subject, document_id)
