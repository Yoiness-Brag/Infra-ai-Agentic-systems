# Layer 2 — Orchestration and Control Plane

## Purpose

L2 is the brain of the system. It decides which agent runs, how multi-agent workflows compose, when execution stops, and how retries and fallbacks behave. L2 owns workflow state, dispatches subtasks across workers, scales worker capacity to demand, and persists the audit-quality record of every reasoning step.

L2 operates the **Orchestrator-Worker pattern** validated by Anthropic Research with a 90.2% measured uplift over single-agent execution: a lead agent on a larger model plans, persists the plan to memory, and dispatches subtasks; subagents on faster models work in parallel in isolated context windows; the lead reconciles findings into the final response.

## Components

L2 is realized by three platform pieces and two service pieces:

**Platform** (infrastructure):

| Component | Purpose |
|---|---|
| **kagent controller** | Reconciles Agent CRDs and ToolServer CRDs into running pods. Provides the agent lifecycle primitives, the prompt-template ConfigMap mechanism, the HITL gate, and the context-compaction primitives. Lives at `platform/kagent-base/`. |
| **NATS JetStream** (3-replica) | Durable message bus for subtask dispatch and result return. Lives at `platform/L2-orchestration/nats-jetstream/`. |
| **KEDA** | Autoscaler that scales `agent-worker` on JetStream consumer lag, not CPU. Lives at `platform/L2-orchestration/keda/`. |

**Services** (workload-aware code that runs on the platform):

| Service | Purpose |
|---|---|
| **agent-orchestrator** | The lead agent. Reads the user request from L1, builds a LangGraph state-machine run, persists the plan to L4 memory, dispatches subtasks on NATS subjects, awaits worker results, reconciles them, streams the final response back to L1. Lives at `services/L3-agent-runtime/agent-orchestrator/` (the service code lives under L3 because its runtime instances are L3; L2 is its dispatching role). |
| **agent-worker** | The subagent. Consumes subtasks from NATS, executes them, calls L4 memory and L5 tools as needed, publishes results back. Horizontally autoscaled by KEDA. Lives at `services/L3-agent-runtime/agent-worker/`. |

## Contracts

### Upstream contract (from L1)

- `agent-orchestrator` exposes `POST /chat/stream` (SSE) on Service `agent-orchestrator.<workload-namespace>`. Body is the user request envelope.

### NATS subjects (the L2 east-west protocol)

| Subject pattern | Direction | Payload | Schema |
|---|---|---|---|
| `agents.subtask.<session_id>` | orchestrator → worker | `SubtaskRequest` envelope (subtask id, parent run id, context handle, tool allowlist, model hint, deadline) | `shared/proto/asyncapi/subtask-request.yaml` |
| `agents.result.<session_id>` | worker → orchestrator | `SubtaskResult` envelope (subtask id, status, result handle to L4 memory, tokens used, error if any) | `shared/proto/asyncapi/subtask-result.yaml` |
| `memory.ingest.<workload_app>` | any service → memory-svc | Episode payload for asynchronous Graphiti ingestion | `shared/proto/asyncapi/memory-ingest.yaml` |
| `audit.<service>.<action>` | any service → ClickHouse via Langfuse Worker | Audit record | `shared/proto/asyncapi/audit-event.yaml` |

Subject naming is hierarchical so NATS wildcards work: a tooling MCP server can subscribe to `agents.subtask.*` to observe all subtasks across all sessions.

### Downstream contracts

- L4 memory: HTTP to `memory-svc.ai-platform`. Read-only and read-write methods.
- L5 tools: HTTP to `mcp-sandbox-runner.ai-platform` for tool invocations.
- LLM calls: HTTP to Kong's `ai-proxy-advanced` endpoint (loop-back through L1 to get the multi-provider routing).
- L7 telemetry: OTLP to `otel-collector.ai-observability:4317`.

## Distributed-system properties (L2 commitments)

- **At-least-once delivery** on every NATS subject. Every consumer maintains an idempotency dedup table in Redis under `dedup:agents:*` with TTL > redelivery window.
- **Ack budgets**: workers consume with `MaxAckPending=50` per pod; KEDA scales out when consumer lag exceeds threshold.
- **Subtask timeout**: every subtask carries a deadline; workers honor it. The orchestrator marks late results stale and reconciles without them.
- **Circuit breaker**: orchestrator wraps every external call (memory-svc, mcp-sandbox-runner, Kong LLM proxy) with a breaker.
- **Workflow checkpointing**: LangGraph state is persisted to Postgres via `langgraph-checkpoint-postgres`. Crashes mid-run resume from the last checkpoint.
- **Graceful shutdown**: SIGTERM drains in-flight requests, acks pending NATS messages, closes connection pools, then exits.

## Service-level objectives

| SLO | Target |
|---|---|
| `agent-orchestrator` p99 added latency (excluding LLM time) | < 100 ms |
| NATS message round-trip (publish to ack) p99 | < 50 ms |
| Subtask dispatch fan-out time | < 100 ms for up to 10 subtasks |
| KEDA scale-up reaction time on lag spike | < 30 s |
| Workflow checkpoint write p99 | < 50 ms |

## Out of scope

- The actual agent reasoning. Belongs to L3 (the runtime where `agent-orchestrator` and `agent-worker` execute).
- Memory storage. Belongs to L4.
- Tool execution. Belongs to L5.
- The decision of which LLM provider serves a given call. Belongs to L1's `ai-proxy-advanced`.

## See also

- ADR-0007: NATS JetStream as the east-west message bus.
- ADR-0011: Adopt kagent as the base agentic platform.
- `FLOW.mmd` — orchestrator-worker dispatch and reconcile flow.
- `components.md` — exact kagent / NATS / KEDA configurations.
- `runbook.md` — deploy, observe NATS lag, manually drain a worker, recover from checkpoint corruption.

## Status

Documentation contract in place at Stage 00. NATS and KEDA land at Stage 04. kagent base lands at Stage 06. Services land at Stage 07.
