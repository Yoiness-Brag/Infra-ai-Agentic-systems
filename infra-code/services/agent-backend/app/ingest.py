"""Durable document-ingestion worker.

A 200-page PDF is several hundred sequential Gemini extraction calls, which is
far past any HTTP timeout, so ingestion never runs inline. The platform target
is NATS JetStream + KEDA (Stage 04/08); until that exists the job ledger lives
in Postgres and jobs are claimed with ``SELECT ... FOR UPDATE SKIP LOCKED``.
That survives pod restarts, is safe across replicas, and upgrades cleanly to a
real bus later.
"""

from __future__ import annotations

import asyncio
import logging
import time

from .chunking import chunk_pages
from .config import Settings
from .memory import MemoryStore
from .metrics import INGEST_CHUNKS, INGEST_DURATION, INGEST_JOBS
from .pdf import InvalidPdfError, extract_pages
from .sessions import SessionStore
from .storage import ObjectStore

logger = logging.getLogger("agent_backend.ingest")


class IngestWorker:
    """Background loop that turns queued documents into graph episodes."""

    def __init__(
        self,
        settings: Settings,
        sessions: SessionStore,
        storage: ObjectStore,
        memory: MemoryStore,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._storage = storage
        self._memory = memory
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        """Launch the polling loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="ingest-worker")

    async def stop(self) -> None:
        """Signal the loop to finish and wait for it to drain."""
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        """Poll for queued jobs until cancelled."""
        logger.info("ingest worker started")
        while not self._stopping.is_set():
            try:
                claimed = await self._claim_and_process()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - the loop must never die
                logger.error("ingest loop error", extra={"err": exc.__class__.__name__})
                claimed = False
            if not claimed:
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=self._settings.ingest_poll_seconds
                    )
                except TimeoutError:
                    pass
        logger.info("ingest worker stopped")

    async def _claim_and_process(self) -> bool:
        """Claim one job if available. Returns True when work was done."""
        if not (self._sessions.connected and self._storage.connected and self._memory.connected):
            return False
        job = await self._sessions.claim_job(self._settings.ingest_max_attempts)
        if job is None:
            return False
        await self._process(str(job["job_id"]), str(job["document_id"]))
        return True

    async def _process(self, job_id: str, document_id: str) -> None:
        """Extract, chunk and ingest one document."""
        started = time.perf_counter()
        total = 0
        done = 0
        try:
            record = await self._sessions.get_document_for_job(document_id)
            if record is None:
                await self._sessions.finish_job(job_id, "failed", 0, 0, "document row missing")
                INGEST_JOBS.labels(state="failed").inc()
                return

            data = await self._storage.get(str(record["object_key"]))
            pages = extract_pages(data, self._settings.max_pdf_pages)
            chunks = chunk_pages(
                pages, self._settings.chunk_size, self._settings.chunk_overlap
            )
            total = len(chunks)
            group_id = str(record["group_id"])
            filename = str(record["filename"])

            if total == 0:
                await self._sessions.finish_job(
                    job_id, "empty", 0, 0, "no extractable text (scanned PDF?)"
                )
                INGEST_JOBS.labels(state="empty").inc()
                logger.warning("document had no text layer", extra={"document_id": document_id})
                return

            semaphore = asyncio.Semaphore(self._settings.ingest_concurrency)
            counter = _Counter()

            async def ingest_one(chunk) -> None:
                async with semaphore:
                    try:
                        await self._memory.add_document_chunk(
                            group_id=group_id,
                            text=chunk.text,
                            chunk_index=chunk.index,
                            source_description=f"pdf:{filename}#p{chunk.first_page}",
                        )
                        INGEST_CHUNKS.labels(outcome="ok").inc()
                        await counter.bump(self._sessions, job_id, total)
                    except Exception as exc:  # noqa: BLE001 - one chunk must not kill the job
                        INGEST_CHUNKS.labels(outcome="error").inc()
                        logger.warning(
                            "chunk ingest failed",
                            extra={"chunk": chunk.index, "err": exc.__class__.__name__},
                        )

            await asyncio.gather(*(ingest_one(c) for c in chunks))
            done = counter.value

            state = "completed" if done == total else "partial"
            await self._sessions.finish_job(job_id, state, total, done, None)
            INGEST_JOBS.labels(state=state).inc()
            logger.info(
                "document ingested",
                extra={"document_id": document_id, "chunks": total, "ok": done},
            )
        except InvalidPdfError as exc:
            await self._sessions.finish_job(job_id, "failed", total, done, str(exc))
            INGEST_JOBS.labels(state="failed").inc()
        except Exception as exc:  # noqa: BLE001
            state = await self._sessions.requeue_job(
                job_id, self._settings.ingest_max_attempts, exc.__class__.__name__
            )
            if state == "failed":
                INGEST_JOBS.labels(state="failed").inc()
            logger.error(
                "ingest job error",
                extra={"job_id": job_id, "state": state, "err": exc.__class__.__name__},
            )
        finally:
            INGEST_DURATION.observe(time.perf_counter() - started)


class _Counter:
    """Chunk counter that reports progress every 10 chunks."""

    def __init__(self) -> None:
        self.value = 0
        self._lock = asyncio.Lock()

    async def bump(self, sessions: SessionStore, job_id: str, total: int) -> None:
        async with self._lock:
            self.value += 1
            current = self.value
        if current % 10 == 0:
            try:
                await sessions.job_progress(job_id, total, current)
            except Exception as exc:  # noqa: BLE001 - progress is advisory
                logger.debug(
                    "progress update skipped", extra={"err": exc.__class__.__name__}
                )
