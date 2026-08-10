"""mcp-graphiti-memory — FastMCP STREAMABLE_HTTP server (port 3002, path /mcp).

Wraps Graphiti-on-FalkorDB (Gemini LLM + Gemini embedder) and exposes two MCP
tools for the kagent MVP agent:

    memory_search(query: str, group_id: str) -> list[dict]
    memory_add_episode(text: str, group_id: str, role: str = "user") -> str

``group_id`` partitions memory per session (SPEC §9: group_id == session_id).

Fail-closed: the process refuses to start if GOOGLE_API_KEY is empty (SPEC §6).

kagent connects over ``protocol: STREAMABLE_HTTP`` to
``http://mcp-graphiti-memory.ai-platform:3002/mcp``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
from graphiti_core.nodes import EpisodeType
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("mcp-graphiti-memory")

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "3002"))

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY.strip():
    logger.error("GOOGLE_API_KEY is empty — refusing to start (fail-closed).")
    sys.exit(1)

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "falkordb.ai-platform")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
FALKORDB_PASSWORD = os.getenv("FALKORDB_PASSWORD") or None

GEMINI_LLM_MODEL = os.getenv("GEMINI_LLM_MODEL", "gemini-2.5-flash")
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
SEARCH_NUM_RESULTS = max(1, min(int(os.getenv("SEARCH_NUM_RESULTS", "10")), 50))
OP_TIMEOUT = float(os.getenv("GRAPHITI_OP_TIMEOUT", "60.0"))

mcp = FastMCP(
    "mcp-graphiti-memory",
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
)

_graphiti: Graphiti | None = None
_indices_ready = False
_client_lock = asyncio.Lock()


def _build_client() -> Graphiti:
    driver = FalkorDriver(
        host=FALKORDB_HOST,
        port=FALKORDB_PORT,
        password=FALKORDB_PASSWORD,
    )
    return Graphiti(
        graph_driver=driver,
        llm_client=GeminiClient(
            config=LLMConfig(api_key=GOOGLE_API_KEY, model=GEMINI_LLM_MODEL)
        ),
        embedder=GeminiEmbedder(
            config=GeminiEmbedderConfig(
                api_key=GOOGLE_API_KEY, embedding_model=GEMINI_EMBED_MODEL
            )
        ),
    )


async def _get_client() -> Graphiti:
    """Lazily build the client and ensure indices exist (idempotent, serialized)."""
    global _graphiti, _indices_ready
    async with _client_lock:
        if _graphiti is None:
            _graphiti = _build_client()
        if not _indices_ready:
            try:
                await asyncio.wait_for(
                    _graphiti.build_indices_and_constraints(), timeout=OP_TIMEOUT
                )
            except Exception as exc:
                logger.warning("build_indices_and_constraints: %s", exc)
            _indices_ready = True
    return _graphiti


@mcp.tool()
async def memory_search(query: str, group_id: str) -> list[dict]:
    """Search session memory (Graphiti graph) for facts relevant to a query.

    Args:
        query: Natural-language query to search the memory graph.
        group_id: Session partition key (== session_id). Required.

    Returns:
        A list of ``{"fact", "uuid", "valid_at", "source_node_uuid",
        "target_node_uuid"}`` dicts. Empty list if nothing is found or on error.
    """
    if not isinstance(query, str) or not query.strip():
        return []
    if not isinstance(group_id, str) or not group_id.strip():
        raise ValueError("group_id is required")

    try:
        client = await _get_client()
        edges = await asyncio.wait_for(
            client.search(
                query=query,
                group_ids=[group_id],
                num_results=SEARCH_NUM_RESULTS,
            ),
            timeout=OP_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("memory_search timed out after %ss", OP_TIMEOUT)
        return []
    except Exception as exc:
        logger.error("memory_search failed: %s", type(exc).__name__)
        return []

    results: list[dict] = []
    for edge in edges:
        valid_at = getattr(edge, "valid_at", None)
        results.append(
            {
                "fact": getattr(edge, "fact", ""),
                "uuid": getattr(edge, "uuid", ""),
                "valid_at": valid_at.isoformat() if valid_at else None,
                "source_node_uuid": getattr(edge, "source_node_uuid", ""),
                "target_node_uuid": getattr(edge, "target_node_uuid", ""),
            }
        )
    return results


@mcp.tool()
async def memory_add_episode(text: str, group_id: str, role: str = "user") -> str:
    """Add a conversational episode to session memory.

    Args:
        text: The message/episode body to store.
        group_id: Session partition key (== session_id). Required.
        role: Who produced the text ("user" or "assistant"); default "user".

    Returns:
        The UUID of the stored episodic node, or "" on error.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text is required")
    if not isinstance(group_id, str) or not group_id.strip():
        raise ValueError("group_id is required")
    role = role if isinstance(role, str) and role.strip() else "user"

    try:
        client = await _get_client()
        result = await asyncio.wait_for(
            client.add_episode(
                name=f"{role}-message",
                episode_body=text,
                source=EpisodeType.message,
                source_description=f"mcp-graphiti-memory ({role})",
                reference_time=datetime.now(timezone.utc),
                group_id=group_id,
            ),
            timeout=OP_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("memory_add_episode timed out after %ss", OP_TIMEOUT)
        return ""
    except Exception as exc:
        logger.error("memory_add_episode failed: %s", type(exc).__name__)
        return ""

    episode = getattr(result, "episode", None)
    return getattr(episode, "uuid", "") if episode is not None else ""


if __name__ == "__main__":
    logger.info(
        "starting mcp-graphiti-memory on %s:%s path /mcp (falkordb=%s:%s)",
        HOST,
        PORT,
        FALKORDB_HOST,
        FALKORDB_PORT,
    )
    mcp.run(transport="streamable-http")
