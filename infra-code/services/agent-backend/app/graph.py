"""LangGraph turn orchestration with FalkorDB-backed checkpoints.

The graph is deliberately small — recall, delegate, persist — because the
reasoning loop itself lives in the kagent Agent behind A2A. What LangGraph buys
here is durable, resumable turn state: if the pod dies between the A2A call and
the memory write, the checkpoint lets the turn resume instead of double-charging
the LLM.

Checkpoint backend
------------------
``langgraph-checkpoint-redis`` cannot be used against FalkorDB: it requires the
RedisJSON and RediSearch modules (it issues ``FT.CREATE`` in ``setup()`` and
``JSON.SET`` on every write), and the FalkorDB image loads only ``falkordb.so``.
FalkorDB's own ``langchain-falkordb`` package ships ``FalkorDBSaver``, which
stores checkpoints as Cypher nodes, so that is what we use. If it cannot be
imported or initialised the graph falls back to an in-memory saver and logs
loudly rather than refusing to serve.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .a2a_client import A2AClient, A2AResult
from .config import Settings
from .memory import MemoryStore
from .metrics import A2A_CALL_COUNT, ERROR_COUNT

logger = logging.getLogger("agent_backend.graph")


def _last_wins(_current: Any, incoming: Any) -> Any:
    return incoming


class TurnState(TypedDict, total=False):
    """State carried through one conversational turn."""

    session_id: Annotated[str, _last_wins]
    subject: Annotated[str, _last_wins]
    message: Annotated[str, _last_wins]
    turn_key: Annotated[str, _last_wins]
    group_ids: Annotated[list[str], _last_wins]
    session_group_id: Annotated[str, _last_wins]
    memory_context: Annotated[list[str], _last_wins]
    answer: Annotated[str, _last_wins]
    context_id: Annotated[str | None, _last_wins]


def build_checkpointer(settings: Settings):
    """Return a LangGraph checkpointer, preferring FalkorDB."""
    if settings.checkpoint_backend == "memory":
        logger.warning("CHECKPOINT_BACKEND=memory — turn state will not survive restarts")
        return InMemorySaver()
    try:
        from langchain_falkordb.checkpoint import FalkorDBSaver
    except ImportError:
        logger.error(
            "langchain-falkordb is not installed; falling back to InMemorySaver. "
            "Checkpoints will not survive a restart."
        )
        return InMemorySaver()
    try:
        saver = FalkorDBSaver(
            host=settings.falkordb_host,
            port=settings.falkordb_port,
            password=settings.falkordb_password or None,
        )
    except Exception as exc:  # noqa: BLE001 - never block startup on the checkpointer
        logger.error(
            "FalkorDBSaver init failed; falling back to InMemorySaver",
            extra={"err": exc.__class__.__name__},
        )
        return InMemorySaver()
    logger.info("checkpointer: FalkorDBSaver", extra={"host": settings.falkordb_host})
    return saver


def build_graph(
    settings: Settings,
    memory: MemoryStore,
    a2a: A2AClient,
    checkpointer,
):
    """Compile the turn graph."""

    async def recall(state: TurnState) -> TurnState:
        """Search the session partition and this subject's document partitions."""
        try:
            facts = await memory.search(
                group_ids=state.get("group_ids", []),
                query=state["message"],
                limit=6,
            )
        except Exception as exc:  # noqa: BLE001 - degraded recall must not fail the turn
            logger.warning("memory search failed", extra={"err": exc.__class__.__name__})
            ERROR_COUNT.labels(path="/chat", type="memory_search").inc()
            facts = []
        return {"memory_context": facts}

    async def delegate(state: TurnState) -> TurnState:
        """Call the kagent Agent over A2A."""
        result: A2AResult = await a2a.send(
            message=state["message"],
            memory_context=state.get("memory_context", []),
            context_id=state.get("context_id"),
        )
        A2A_CALL_COUNT.labels(outcome="success").inc()
        return {"answer": result.text, "context_id": result.context_id}

    async def persist(state: TurnState) -> TurnState:
        """Write both turns into the session partition."""
        group_id = state["session_group_id"]
        turn = state.get("turn_key", "0")
        try:
            await memory.add_turn(group_id, state["message"], "user", turn)
            await memory.add_turn(group_id, state["answer"], "assistant", turn)
        except Exception as exc:  # noqa: BLE001 - the answer is already earned
            logger.error("memory persist failed", extra={"err": exc.__class__.__name__})
            ERROR_COUNT.labels(path="/chat", type="memory_persist").inc()
        return {}

    builder = StateGraph(TurnState)
    builder.add_node("recall", recall)
    builder.add_node("delegate", delegate)
    builder.add_node("persist", persist)
    builder.add_edge(START, "recall")
    builder.add_edge("recall", "delegate")
    builder.add_edge("delegate", "persist")
    builder.add_edge("persist", END)
    return builder.compile(checkpointer=checkpointer)
