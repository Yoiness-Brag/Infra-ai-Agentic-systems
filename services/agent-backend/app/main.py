"""FastAPI agent-backend.

Owns auth + sessions + memory; delegates reasoning to a kagent Agent over A2A.

Endpoints:
  POST /chat     authed; upsert session -> memory.search -> A2A -> stream SSE,
                 then persist user + result episodes.
  GET  /healthz  liveness (process up).
  GET  /readyz   readiness (Postgres + FalkorDB + kagent reachable).
  GET  /metrics  Prometheus exposition.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from .a2a_client import A2AClient, CircuitOpenError
from .auth import verify_token
from .config import Settings, get_settings
from .logging_config import configure_logging, request_id_var
from .memory import MemoryStore
from .metrics import A2A_CALL_COUNT, ERROR_COUNT, REQUEST_COUNT, REQUEST_LATENCY
from .sessions import SessionStore

logger = logging.getLogger("agent_backend.main")

_REQUEST_ID_HEADER = "x-request-id"


class ChatRequest(BaseModel):
    """Request body for ``POST /chat``."""

    session_id: str | None = Field(default=None, description="UUID; minted if absent.")
    message: str = Field(min_length=1, max_length=16_000)

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: str | None) -> str | None:
        """Reject a client-supplied session id that is not a valid UUID."""
        if value is None:
            return None
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("session_id must be a valid UUID") from exc


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open dependency clients on startup and drain them on shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)

    sessions = SessionStore(settings)
    memory = MemoryStore(settings)
    a2a = A2AClient(settings)

    await sessions.connect()
    await memory.connect()
    await a2a.connect()

    app.state.settings = settings
    app.state.sessions = sessions
    app.state.memory = memory
    app.state.a2a = a2a
    logger.info("agent-backend started")
    try:
        yield
    finally:
        await a2a.close()
        await memory.close()
        await sessions.close()
        logger.info("agent-backend stopped")


app = FastAPI(title="agent-backend", lifespan=lifespan)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Correlate, time, and count every request; never swallow exceptions."""
    request_id = request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        ERROR_COUNT.labels(path=request.url.path, type=exc.__class__.__name__).inc()
        REQUEST_COUNT.labels(request.method, request.url.path, "500").inc()
        raise
    finally:
        REQUEST_LATENCY.labels(request.method, request.url.path).observe(
            time.perf_counter() - start
        )
        request_id_var.reset(token)
    REQUEST_COUNT.labels(
        request.method, request.url.path, str(response.status_code)
    ).inc()
    response.headers[_REQUEST_ID_HEADER] = request_id
    return response


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe — returns ok while the process is running."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    """Readiness probe — fails when a required dependency is unreachable."""
    checks: dict[str, str] = {}
    ok = True

    async def _check(name: str, coro) -> None:
        nonlocal ok
        try:
            await coro
            checks[name] = "ok"
        except Exception as exc:  # noqa: BLE001
            ok = False
            checks[name] = f"error: {exc.__class__.__name__}"
            logger.warning("readiness check failed", extra={"dep": name, "err": str(exc)})

    await _check("postgres", request.app.state.sessions.ping())
    await _check("falkordb", request.app.state.memory.ping())

    if request.app.state.a2a.breaker_open:
        ok = False
        checks["kagent_a2a"] = "error: circuit_open"
    else:
        checks["kagent_a2a"] = "ok"

    status_code = status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        {"status": "ok" if ok else "degraded", "checks": checks}, status_code=status_code
    )


@app.get("/metrics")
async def metrics() -> PlainTextResponse:
    """Expose Prometheus metrics in text exposition format."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    subject: str = Depends(verify_token),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """Authenticated turn: upsert session, recall memory, delegate over A2A, stream."""
    sessions: SessionStore = request.app.state.sessions
    memory: MemoryStore = request.app.state.memory
    a2a: A2AClient = request.app.state.a2a

    session_id = body.session_id or _new_session_id()

    await sessions.upsert(
        session_id=session_id,
        subject=subject,
        app=settings.workload_app,
        meta={"last_message_len": len(body.message)},
    )

    try:
        memory_context = await memory.search(session_id, body.message)
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory search failed", extra={"err": str(exc)})
        ERROR_COUNT.labels(path="/chat", type="memory_search").inc()
        memory_context = []

    try:
        answer = await a2a.send(
            message=body.message,
            memory_context=memory_context,
            context_id=session_id,
        )
        A2A_CALL_COUNT.labels(outcome="success").inc()
    except CircuitOpenError as exc:
        A2A_CALL_COUNT.labels(outcome="circuit_open").inc()
        ERROR_COUNT.labels(path="/chat", type="circuit_open").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent temporarily unavailable",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        A2A_CALL_COUNT.labels(outcome="error").inc()
        ERROR_COUNT.labels(path="/chat", type="a2a").inc()
        logger.error("a2a call failed", extra={"err": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="agent call failed"
        ) from exc

    try:
        await memory.add_episode(session_id, body.message, role="user")
        await memory.add_episode(session_id, answer, role="assistant")
    except Exception as exc:  # noqa: BLE001
        logger.error("memory persist failed", extra={"err": str(exc)})
        ERROR_COUNT.labels(path="/chat", type="memory_persist").inc()

    async def event_stream() -> AsyncIterator[dict]:
        yield {"event": "session", "data": session_id}
        yield {"event": "message", "data": answer}
        yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_stream())


def _new_session_id() -> str:
    """Return a UUIDv7 when available (Python 3.14+), else a UUIDv4."""
    factory = getattr(uuid, "uuid7", uuid.uuid4)
    return str(factory())
