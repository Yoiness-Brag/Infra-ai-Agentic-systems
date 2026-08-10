# Stage 07 — Agent Runtime (port from reference workload)

## Goal

Port the reference workload from FareedKhan-dev/production-grade-agentic-system into the platform shape. Split the monolith into agent-orchestrator (lead) and agent-worker (subagent). Wire up NATS subjects, LangGraph checkpointing to Postgres, Kong front, OTel back. This is the stage where the platform first does useful work.

## Depends on

Stage 06; the lift inventory is at `docs/reference/upstream-repo-mapping.md`.

## Deliverables

- `services/L3-agent-runtime/agent-orchestrator/` with the LangGraph state machine, FastAPI front, NATS publisher, Postgres checkpointer.
- `services/L3-agent-runtime/agent-worker/` with the NATS consumer, LangGraph node executor.
- `shared/py-common/` with `logging.py`, `middleware.py`, `telemetry.py`, `sanitization.py` ported from the reference workload.
- Agent CRDs defining the orchestrator and worker.
- Kong route to the orchestrator.
- End-to-end test: a chat request reaches the orchestrator, dispatches subtasks, workers execute, response streams back.

## Non-goals

- No memory layer yet; Stage 08 brings memory-svc. The reference workload's mem0 import is REMOVED (not stubbed) per ADR-0004; agent-orchestrator and agent-worker call `memory-svc` directly starting Stage 08.

## Acceptance criteria

1. End-to-end `POST /chat/stream` returns a coherent streamed response.
2. NATS consumer lag stays bounded under synthetic load.
3. Langfuse shows the run as a trace tree.
4. Postgres has a LangGraph checkpoint per run.

## Next stage

Stage 08 (Memory) and Stage 09 (Tools and sandbox).
