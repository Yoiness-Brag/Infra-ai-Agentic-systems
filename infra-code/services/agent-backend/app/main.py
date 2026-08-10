"""FastAPI agent-backend.

Owns auth, sessions, the memory graph and document ingestion; delegates
reasoning to a kagent Agent over A2A, orchestrated by a small LangGraph with
FalkorDB-backed checkpoints.

Endpoints
  POST /chat        authed; SSE envelope
  POST /chat/sync   authed; plain JSON (usable from Swagger UI)
  POST /documents   authed; PDF -> MinIO -> memory graph
  GET  /healthz     liveness
  GET  /readyz      readiness (dependency reachability)
  GET  /metrics     Prometheus exposition
  GET  /docs        Swagger UI
"""

from __future__ import annotations

import asyncio
import hashlib
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

from .a2a_client import A2AClient, A2AProtocolError, A2ARemoteError
from .auth import verify_token
from .config import Settings, get_settings
from .documents import router as documents_router
from .graph import build_checkpointer, build_graph
from .logging_config import configure_logging, request_id_var
from .memory import MemoryStore
from .metrics import (
    A2A_CALL_COUNT,
    ERROR_COUNT,
    IN_FLIGHT,
    REQUEST_COUNT,
    REQUEST_LATENCY,
)
from .resilience import CircuitOpenError
from .sessions import SessionOwnershipError, SessionStore
from .storage import ObjectStore

logger = logging.getLogger("agent_backend.main")

_REQUEST_ID_HEADER = "x-request-id"
_UNMATCHED = "__unmatched__"

_OPENAPI_DESCRIPTION = """
Agent backend for the Infra-AI platform.

* **Auth** — every endpoint except `/healthz`, `/readyz`, `/metrics` and the docs
  requires `Authorization: Bearer <HS256 JWT>` with `iss` matching `JWT_ISS`.
  Mint one locally with `make token`.
* **Sessions** live in Postgres. **Conversation memory and document knowledge**
  live in the FalkorDB graph. **PDF objects** live in MinIO.
* `/chat` returns a single-shot SSE envelope. Swagger UI cannot render SSE, so
  use `/chat/sync` from this page.
"""


class ChatRequest(BaseModel):
    """Request body for a chat turn."""

    session_id: str | None = Field(
        default=None, description="UUID of an existing session; minted when absent."
    )
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


class ChatResponse(BaseModel):
    """Non-streaming chat reply."""

    session_id: str
    answer: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Wire dependencies. Connection happens in the background so the pod stays
    schedulable and observable while a dependency is still coming up."""
    settings = get_settings()
    configure_logging(settings.log_level)

    sessions = SessionStore(settings)
    memory = MemoryStore(settings)
    storage = ObjectStore(settings)
    a2a = A2AClient(settings)

    app.state.settings = settings
    app.state.sessions = sessions
    app.state.memory = memory
    app.state.storage = storage
    app.state.a2a = a2a
    app.state.graph = None
    app.state.ingest = None

    connector = asyncio.create_task(_connect_all(app), name="connect-dependencies")
    logger.info("agent-backend starting")
    try:
        yield
    finally:
        connector.cancel()
        if app.state.ingest is not None:
            await app.state.ingest.stop()
        await a2a.close()
        await storage.close()
        await memory.close()
        await sessions.close()
        logger.info("agent-backend stopped")


async def _connect_all(app: FastAPI) -> None:
    """Connect every dependency with backoff, then start the ingest worker."""
    from .ingest import IngestWorker

    settings: Settings = app.state.settings
    targets = (
        ("postgres", app.state.sessions.connect),
        ("minio", app.state.storage.connect),
        ("a2a", app.state.a2a.connect),
        ("falkordb", app.state.memory.connect),
    )
    delay = 1.0
    pending = list(targets)
    while pending:
        still: list = []
        for name, connect in pending:
            try:
                await connect()
                logger.info("dependency connected", extra={"dep": name})
            except Exception as exc:  # noqa: BLE001 - retry forever, never crash
                logger.warning(
                    "dependency not ready",
                    extra={"dep": name, "err": exc.__class__.__name__},
                )
                still.append((name, connect))
        pending = still
        if pending:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)

    await app.state.a2a.fetch_agent_card()

    app.state.graph = build_graph(
        settings, app.state.memory, app.state.a2a, build_checkpointer(settings)
    )
    worker = IngestWorker(settings, app.state.sessions, app.state.storage, app.state.memory)
    worker.start()
    app.state.ingest = worker
    logger.info("agent-backend ready")


app = FastAPI(
    title="agent-backend",
    version="1.0.0",
    description=_OPENAPI_DESCRIPTION,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "chat", "description": "Conversational turns."},
        {"name": "documents", "description": "PDF upload and ingestion."},
        {"name": "ops", "description": "Health and metrics."},
    ],
)
app.include_router(documents_router)


def _route_label(request: Request) -> str:
    """Return the matched route template, never the raw path.

    Using the raw path would mint a new Prometheus series for every scanner
    probe (`/.env`, `/wp-login.php`, ...) and eventually OOM Prometheus.
    """
    route = request.scope.get("route")
    return getattr(route, "path", None) or _UNMATCHED


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Correlate, time and count every request; never swallow exceptions."""
    request_id = request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    instrument = request.url.path not in ("/metrics", "/healthz", "/readyz")
    if instrument:
        IN_FLIGHT.labels(path=request.url.path).inc()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001
        ERROR_COUNT.labels(path=_route_label(request), type=exc.__class__.__name__).inc()
        REQUEST_COUNT.labels(request.method, _route_label(request), "500").inc()
        raise
    finally:
        if instrument:
            IN_FLIGHT.labels(path=request.url.path).dec()
            REQUEST_LATENCY.labels(request.method, _route_label(request)).observe(
                time.perf_counter() - start
            )
        request_id_var.reset(token)
    REQUEST_COUNT.labels(
        request.method, _route_label(request), str(response.status_code)
    ).inc()
    response.headers[_REQUEST_ID_HEADER] = request_id
    return response


@app.get("/healthz", tags=["ops"], summary="Liveness")
async def healthz() -> dict[str, str]:
    """Liveness probe — ok while the process is running."""
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"], summary="Readiness")
async def readyz(request: Request) -> JSONResponse:
    """Readiness probe.

    Reports dependency reachability. Deliberately NOT gated on the A2A circuit
    breaker: failing readiness on a downstream breaker removes the pod from the
    Service, which stops all traffic, which prevents the probe that would close
    the breaker — a permanent deadlock at one replica. `/chat` returns 503 on an
    open breaker instead, which is the correct blast radius.
    """
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

    if request.app.state.graph is None:
        ok = False
        checks["startup"] = "connecting"

    await _check("postgres", request.app.state.sessions.ping())
    await _check("falkordb", request.app.state.memory.ping())
    await _check("minio", request.app.state.storage.ping())
    checks["kagent_a2a"] = "breaker_open" if request.app.state.a2a.breaker_open else "ok"

    return JSONResponse(
        {"status": "ok" if ok else "degraded", "checks": checks},
        status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@app.get("/metrics", tags=["ops"], summary="Prometheus metrics")
async def metrics() -> PlainTextResponse:
    """Expose Prometheus metrics in text exposition format."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def _run_turn(
    request: Request, body: ChatRequest, subject: str, settings: Settings
) -> tuple[str, str]:
    """Execute one turn through the LangGraph and return (session_id, answer)."""
    sessions: SessionStore = request.app.state.sessions
    graph = request.app.state.graph
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="backend still connecting to its dependencies",
        )

    session_id = body.session_id or _new_session_id()

    try:
        await sessions.upsert(
            session_id=session_id,
            subject=subject,
            app=settings.workload_app,
            meta={"last_message_len": len(body.message)},
        )
    except SessionOwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="session_id belongs to a different subject",
        ) from exc
    except CircuitOpenError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="session store unavailable"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        ERROR_COUNT.labels(path="/chat", type="session_upsert").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="session store unavailable"
        ) from exc

    session_group = settings.session_group_id(session_id)
    state = {
        "session_id": session_id,
        "subject": subject,
        "message": body.message,
        "turn_key": hashlib.sha256(body.message.encode()).hexdigest()[:16],
        "session_group_id": session_group,
        "group_ids": [session_group],
        "memory_context": [],
    }
    config = {
        "configurable": {
            "thread_id": f"{settings.workload_app}:{session_id}",
            "checkpoint_ns": "",
        }
    }

    try:
        async with asyncio.timeout(settings.request_budget_seconds):
            result = await graph.ainvoke(state, config=config)
    except TimeoutError as exc:
        ERROR_COUNT.labels(path="/chat", type="budget_exceeded").inc()
        A2A_CALL_COUNT.labels(outcome="timeout").inc()
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="turn exceeded the request budget",
        ) from exc
    except CircuitOpenError as exc:
        A2A_CALL_COUNT.labels(outcome="circuit_open").inc()
        ERROR_COUNT.labels(path="/chat", type="circuit_open").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent temporarily unavailable",
        ) from exc
    except (A2ARemoteError, A2AProtocolError) as exc:
        A2A_CALL_COUNT.labels(outcome="error").inc()
        ERROR_COUNT.labels(path="/chat", type="a2a").inc()
        logger.error("a2a call failed", extra={"err": exc.__class__.__name__})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="agent call failed"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        A2A_CALL_COUNT.labels(outcome="error").inc()
        ERROR_COUNT.labels(path="/chat", type="turn").inc()
        logger.error("turn failed", extra={"err": exc.__class__.__name__})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="agent call failed"
        ) from exc

    return session_id, str(result.get("answer", ""))


@app.post(
    "/chat",
    tags=["chat"],
    summary="Chat turn (SSE envelope)",
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "SSE envelope"},
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "session_id belongs to another subject"},
        502: {"description": "Agent call failed"},
        503: {"description": "Dependency unavailable or breaker open"},
        504: {"description": "Turn exceeded REQUEST_BUDGET_SECONDS"},
    },
)
async def chat(
    body: ChatRequest,
    request: Request,
    subject: str = Depends(verify_token),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """Run a turn and return it as a single-shot SSE envelope.

    The whole turn completes before the stream opens; true token streaming needs
    A2A `message/stream`, which kagent's compat path does not expose here.
    """
    session_id, answer = await _run_turn(request, body, subject, settings)

    async def event_stream() -> AsyncIterator[dict]:
        yield {"event": "session", "data": session_id}
        yield {"event": "message", "data": answer}
        yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_stream())


@app.post(
    "/chat/sync",
    tags=["chat"],
    summary="Chat turn (plain JSON — use this from Swagger UI)",
    response_model=ChatResponse,
    responses={
        401: {"description": "Missing or invalid bearer token"},
        403: {"description": "session_id belongs to another subject"},
        502: {"description": "Agent call failed"},
        503: {"description": "Dependency unavailable or breaker open"},
        504: {"description": "Turn exceeded REQUEST_BUDGET_SECONDS"},
    },
)
async def chat_sync(
    body: ChatRequest,
    request: Request,
    subject: str = Depends(verify_token),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """Run a turn and return the answer as JSON."""
    session_id, answer = await _run_turn(request, body, subject, settings)
    return ChatResponse(session_id=session_id, answer=answer)


def _new_session_id() -> str:
    """Return a UUIDv7 so ids sort by creation time."""
    try:
        import uuid6

        return str(uuid6.uuid7())
    except ImportError:
        return str(uuid.uuid4())
