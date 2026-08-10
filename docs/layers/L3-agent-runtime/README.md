# Layer 3 — Agent Runtime

## Purpose

L3 is where an agent actually runs. It owns the per-agent context window, the system prompt, the model selection, the tool allowlist, the memory binding, and the human-in-the-loop gate. L3 turns the abstract notion of "an agent" into a concrete Kubernetes workload with bounded resources, observable execution, and a clear lifecycle.

L3 does not decide the multi-agent topology (that is L2). It does not store long-term memory (that is L4). It does not execute tools (that is L5). It is the **execution context** in which one agent's reasoning happens.

## Components

L3 is realized by the kagent control loop plus three platform services:

**Platform** (from the kagent base):

| Component | Purpose |
|---|---|
| **kagent controller** | Reconciles `Agent` CRDs into Deployments. Manages prompt-template ConfigMap references, ToolServer bindings, A2A skill exposure, HITL gates. |
| **Agent CRD** | The declarative unit of an agent. Fields include: `systemPrompt`, `model`, `toolServers`, `memory`, `a2aSkills`, `hitl`. |
| **ToolServer CRD** | A registered MCP tool server. Multiple Agents can reference the same ToolServer. |

**Services** (workload-aware code):

| Service | Purpose |
|---|---|
| **agent-orchestrator** | The lead-agent reference implementation. FastAPI front, LangGraph state machine, Postgres checkpointer. |
| **agent-worker** | The subagent reference implementation. NATS consumer, autoscaled by KEDA, LangGraph state machine, calls memory and tools as required. |
| **a2a-adapter** | The A2A interop layer. Publishes Agent Cards at `/.well-known/agent.json` and accepts JSON-RPC 2.0 task delegations. |

## Contracts

### Upstream contract (from L2)

- `agent-orchestrator` exposes `POST /chat/stream` (SSE) on its Service.
- `agent-worker` consumes NATS subjects `agents.subtask.<session_id>`.

### A2A contract (peer-to-peer ingress and egress)

- `a2a-adapter` exposes `/.well-known/agent.json` per workload, with Agent Cards generated from Agent CRD fields.
- Inbound A2A tasks land at `/a2a/tasks` (JSON-RPC 2.0) and are translated into the same internal envelope as L1-originated requests.
- Outbound A2A calls (one agent delegating to a peer) go through `a2a-adapter` so the same governance, telemetry, and retry policy applies.

### Per-app namespace isolation

Each workload occupies its own Kubernetes namespace. NetworkPolicies block cross-namespace traffic except via these allowed paths:
- → Kong (L1)
- → memory-svc (L4)
- → mcp-sandbox-runner (L5)
- → otel-collector (L7)
- → NATS (L2)
- → a2a-adapter (intra-cluster) for A2A delegation

This realizes the "per-app isolation" property; no workload reads another workload's traffic by accident.

### Downstream contracts

- L4 memory: HTTP to `memory-svc.ai-platform`.
- L5 tools: HTTP to `mcp-sandbox-runner.ai-platform`.
- L7 telemetry: OTLP to `otel-collector.ai-observability:4317`.
- LLM calls: HTTP to Kong's `ai-proxy-advanced` egress endpoint.

## Distributed-system properties (L3 commitments)

- **Context-window discipline**: each agent invocation runs in a fresh context window. The orchestrator dispatches subtasks with **handles** to memory, not raw text dumps. Workers fetch only what they need.
- **Context compaction**: kagent's built-in compaction runs when a conversation exceeds a configured token budget. Older turns are summarized; key facts are promoted to L4 long-term memory via memory-svc.
- **HITL gates**: any tool flagged `requiresApproval: true` in the ToolServer pauses execution and emits an event on `audit.hitl.<workload>`. A human-facing UI consumes the event and replies; kagent resumes the agent run on approval.
- **Resource bounds**: every Agent CRD declares `resources.requests` and `resources.limits` (CPU and memory). OPA Gatekeeper rejects Agents without bounds at admission.
- **Idempotent retries**: every external call carries an idempotency key. Retry policy is exponential backoff with jitter, bounded.

## Service-level objectives

| SLO | Target |
|---|---|
| `agent-orchestrator` cold-start p99 | < 5 s |
| `agent-worker` cold-start p99 | < 3 s |
| HITL gate emit-to-resume latency | bounded by human; instrumented with histogram |
| A2A inbound task accept-to-ack p99 | < 200 ms |
| Per-agent context-window utilization warning | at 80% of model context window |

## Out of scope

- Multi-agent topology (orchestrator-worker, hierarchical, swarm). Belongs to L2.
- Memory storage. Belongs to L4.
- Tool execution and sandboxing. Belongs to L5.
- Policy enforcement at admission and at perimeter. Belongs to L6.
- Telemetry storage and dashboards. Belongs to L7.

## See also

- ADR-0011: Adopt kagent as the base agentic platform.
- ADR-0003: MCP and A2A as the platform protocols.
- `FLOW.mmd` — agent lifecycle from Agent CRD apply to ready pod to completed run.
- `components.md` — kagent Agent CRD field reference; orchestrator and worker module breakdown.
- `runbook.md` — deploy an agent, debug a stuck HITL gate, recover from a crashed worker pool.

## Status

Documentation contract in place at Stage 00. kagent base lands at Stage 06. The orchestrator and worker reference implementations land at Stage 07. A2A adapter lands at Stage 10.
