"""Graphiti-on-FalkorDB session memory.

Each turn is stored as a Graphiti *episode* partitioned by ``group_id =
session_id``. Retrieval is via ``search``. Uses Gemini for the LLM + embedder
(MVP deviation from self-hosted bge-* per SPEC §8).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
from graphiti_core.nodes import EpisodeType

from .config import Settings

logger = logging.getLogger("agent_backend.memory")


class MemoryStore:
    """Wraps a Graphiti client backed by FalkorDB."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graphiti: Graphiti | None = None
        self._lock = asyncio.Lock()
        self._timeout = settings.graphiti_op_timeout_seconds

    async def connect(self) -> None:
        """Initialize the Graphiti client and FalkorDB indices (idempotent, serialized)."""
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
            )
            await asyncio.wait_for(
                graphiti.build_indices_and_constraints(), timeout=self._timeout
            )
            self._graphiti = graphiti
            logger.info("memory store connected", extra={"host": s.falkordb_host})

    async def close(self) -> None:
        """Close the Graphiti client and its FalkorDB driver."""
        if self._graphiti is not None:
            await self._graphiti.close()
            self._graphiti = None

    async def ping(self) -> None:
        """Readiness check — verifies the underlying driver responds."""
        if self._graphiti is None:
            raise RuntimeError("memory store not connected")
        await self._graphiti.driver.execute_query("RETURN 1")

    async def add_episode(self, session_id: str, text: str, role: str) -> None:
        """Persist a single conversational turn as an episode."""
        if self._graphiti is None:
            raise RuntimeError("memory store not connected")
        await asyncio.wait_for(
            self._graphiti.add_episode(
                name=f"{role}-{datetime.now(UTC).isoformat()}",
                episode_body=text,
                source=EpisodeType.message,
                source_description=f"chat:{role}",
                reference_time=datetime.now(UTC),
                group_id=session_id,
            ),
            timeout=self._timeout,
        )

    async def search(self, session_id: str, query: str, limit: int = 5) -> list[str]:
        """Return up to ``limit`` relevant memory facts for this session."""
        if self._graphiti is None:
            raise RuntimeError("memory store not connected")
        results = await asyncio.wait_for(
            self._graphiti.search(
                query=query,
                group_ids=[session_id],
                num_results=limit,
            ),
            timeout=self._timeout,
        )
        return [getattr(r, "fact", str(r)) for r in results]
