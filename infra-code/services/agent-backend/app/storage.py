"""MinIO object storage for uploaded PDFs.

The bucket is created on first connect so no provisioning Job is needed. All
calls run in a worker thread because the MinIO SDK is synchronous, and every
call is bounded and breaker-guarded.
"""

from __future__ import annotations

import asyncio
import io
import logging

from minio import Minio
from minio.error import S3Error

from .config import Settings
from .resilience import Breaker, CircuitOpenError

logger = logging.getLogger("agent_backend.storage")

_OP_TIMEOUT = 30.0


class ObjectStore:
    """Async facade over the synchronous MinIO client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Minio | None = None
        self._bucket = settings.minio_bucket
        self._breaker = Breaker(name="minio", threshold=5, cooldown=20.0)

    async def connect(self) -> None:
        """Create the client and ensure the bucket exists (idempotent)."""
        if self._client is not None:
            return
        s = self._settings
        if not s.minio_access_key or not s.minio_secret_key:
            raise RuntimeError("MINIO_ROOT_USER / MINIO_ROOT_PASSWORD are required")
        client = Minio(
            s.minio_endpoint,
            access_key=s.minio_access_key,
            secret_key=s.minio_secret_key,
            secure=s.minio_secure,
        )
        await asyncio.wait_for(
            asyncio.to_thread(self._ensure_bucket, client), timeout=_OP_TIMEOUT
        )
        self._client = client
        logger.info(
            "object store connected",
            extra={"endpoint": s.minio_endpoint, "bucket": self._bucket},
        )

    def _ensure_bucket(self, client: Minio) -> None:
        if not client.bucket_exists(self._bucket):
            client.make_bucket(self._bucket)
            logger.info("created bucket", extra={"bucket": self._bucket})

    @property
    def connected(self) -> bool:
        """True once the client is built and the bucket verified."""
        return self._client is not None

    async def close(self) -> None:
        """Drop the client reference (the SDK holds no persistent connection)."""
        self._client = None

    def _get(self) -> Minio:
        if self._client is None:
            raise RuntimeError("object store not connected")
        if not self._breaker.allow():
            raise CircuitOpenError("minio circuit breaker is open")
        return self._client

    async def _guarded(self, fn, *args):
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(fn, *args), timeout=_OP_TIMEOUT
            )
        except CircuitOpenError:
            raise
        except Exception:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        return result

    async def ping(self) -> None:
        """Readiness check — confirms the bucket is reachable."""
        client = self._get()
        await self._guarded(client.bucket_exists, self._bucket)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store an object."""
        client = self._get()

        def _put() -> None:
            client.put_object(
                self._bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        await self._guarded(_put)

    async def get(self, key: str) -> bytes:
        """Fetch an object's bytes."""
        client = self._get()

        def _get_object() -> bytes:
            response = None
            try:
                response = client.get_object(self._bucket, key)
                return response.read()
            finally:
                if response is not None:
                    response.close()
                    response.release_conn()

        return await self._guarded(_get_object)

    async def delete(self, key: str) -> None:
        """Remove an object; a missing object is not an error."""
        client = self._get()

        def _remove() -> None:
            try:
                client.remove_object(self._bucket, key)
            except S3Error as exc:
                if exc.code not in ("NoSuchKey", "NoSuchObject"):
                    raise

        await self._guarded(_remove)
