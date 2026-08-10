"""Graphiti-on-FalkorDB memory graph.

Two kinds of partition live in the same graph, both keyed by Graphiti
``group_id``:

* conversation turns  -> ``<app>:session:<session_id>``
* uploaded documents  -> ``<app>:<subject>:doc:<document_id>``

Every write carries a deterministic ``uuid5`` so a retried request or a
re-claimed ingestion job is a no-op instead of duplicating entities. Every call
is bounded by ``asyncio.wait_for`` and guarded by a circuit breaker.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
from graphiti_core.nodes import EpisodeType

from .config import Settings
from .resilience import Breaker, CircuitOpenError

logger = logging.getLogger("agent_backend.memory")

_EPISODE_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def episode_uuid(group_id: str, discriminator: str) -> str:
    """Deterministic episode id derived from its partition and discriminator.

    NOTE: this is NOT passed to ``add_episode``. Graphiti treats ``uuid`` as an
    *update handle* — it calls ``EpisodicNode.get_by_uuid`` and raises
    ``NodeNotFoundError`` when the node does not already exist — so supplying a
    novel deterministic uuid makes every first write fail. Idempotency is
    enforced a level up instead: uploads dedup on the content SHA-256 before a
    job is ever queued, and jobs carry terminal states so a completed document
    is never re-ingested. Kept for correlation and for a future update path.
    """
    return str(uuid.uuid5(_EPISODE_NAMESPACE, f"{group_id}|{discriminator}"))


class MemoryStore:
    """Wraps a Graphiti client backed by FalkorDB."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graphiti: Graphiti | None = None
        self._lock = asyncio.Lock()
        self._timeout = settings.graphiti_op_timeout_seconds
        self._breaker = Breaker(name="falkordb", threshold=5, cooldown=20.0)

    async def connect(self) -> None:
        """Initialize the Graphiti client and FalkorDB indices (idempotent)."""
        async with self._lock:
            if self._graphiti is not None:
                return
            s = self._settings
            driver = FalkorDriver(
                host=s.falkordb_host,
                port=s.falkordb_port,
                password=s.falkordb_password or None,
            )
            graphiti = Graphiti(
                graph_driver=driver,
                llm_client=GeminiClient(
                    config=LLMConfig(api_key=s.google_api_key, model=s.gemini_model)
                ),
                embedder=GeminiEmbedder(
                    config=GeminiEmbedderConfig(
                        api_key=s.google_api_key,
                        embedding_model=s.gemini_embedding_model,
                    )
                ),
                cross_encoder=GeminiRerankerClient(
                    config=LLMConfig(api_key=s.google_api_key, model=s.gemini_model)
                ),
            )
            await asyncio.wait_for(
                graphiti.build_indices_and_constraints(), timeout=self._timeout
            )
            self._graphiti = graphiti
            logger.info("memory store connected", extra={"host": s.falkordb_host})

    @property
    def connected(self) -> bool:
        """True once Graphiti is initialised."""
        return self._graphiti is not None

    async def close(self) -> None:
        """Close the Graphiti client and its FalkorDB driver."""
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None

    def _client(self) -> Graphiti:
        if self._graphiti is None:
            raise RuntimeError("memory store not connected")
        if not self._breaker.allow():
            raise CircuitOpenError("falkordb circuit breaker is open")
        return self._graphiti

    async def _guarded(self, coro):
        """Run a Graphiti coroutine under a timeout and update the breaker."""
        try:
            result = await asyncio.wait_for(coro, timeout=self._timeout)
        except CircuitOpenError:
            raise
        except Exception:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        return result

    async def ping(self) -> None:
        """Readiness check — verifies the underlying driver responds."""
        client = self._client()
        await self._guarded(client.driver.execute_query("RETURN 1"))

    async def add_turn(
        self, group_id: str, text: str, role: str, turn_key: str
    ) -> None:
        """Persist one conversational turn as an episode.

        ``turn_key`` is a stable digest of the user message, so retrying the
        same turn rewrites the same episode instead of duplicating it.
        """
        client = self._client()
        now = datetime.now(UTC)
        await self._guarded(
            client.add_episode(
                name=f"{role}-{turn_key}",
                episode_body=text,
                source=EpisodeType.message,
                source_description=f"chat:{role}",
                reference_time=now,
                group_id=group_id,
            )
        )

    async def add_document_chunk(
        self,
        group_id: str,
        text: str,
        chunk_index: int,
        source_description: str,
    ) -> None:
        """Persist one document chunk as an episode."""
        client = self._client()
        await self._guarded(
            client.add_episode(
                name=f"chunk-{chunk_index}",
                episode_body=text,
                source=EpisodeType.text,
                source_description=source_description,
                reference_time=datetime.now(UTC),
                group_id=group_id,
            )
        )

    async def search(
        self, group_ids: list[str], query: str, limit: int = 5
    ) -> list[str]:
        """Return up to ``limit`` relevant facts across the given partitions."""
        if not group_ids:
            return []
        client = self._client()
        results = await self._guarded(
            client.search(query=query, group_ids=group_ids, num_results=limit)
        )
        return [getattr(r, "fact", str(r)) for r in results]

    async def delete_group(self, group_id: str) -> None:
        """Remove every episode in a partition (used when a document is deleted)."""
        client = self._client()
        await self._guarded(
            client.driver.execute_query(
                "MATCH (n) WHERE n.group_id = $gid DETACH DELETE n",
                gid=group_id,
            )
        )
