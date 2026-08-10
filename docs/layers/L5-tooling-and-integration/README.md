# Layer 5 — Tooling and Integration

## Purpose

L5 is how agents reach into the world. It catalogs available tools, validates tool calls before execution, runs the execution inside a hardware-isolated sandbox, and exposes the workloads themselves to peer agents via A2A. L5 turns "the agent wants to do something" into "something safe just happened."

L5 has two sub-planes: **inward tooling** (an agent inside the platform invokes an external capability) and **outward interop** (a peer agent outside the platform invokes a workload inside the platform). Both run through the same governance and telemetry pipeline.

## Components

**Platform** (infrastructure):

| Component | Purpose |
|---|---|
| **CubeSandbox cluster** | KVM-based microVM sandbox cluster. CubeMaster (orchestrator), Cubelet (per-node lifecycle), CubeProxy (port routing), CubeVS (eBPF inter-sandbox isolation), CubeShim (containerd Shim v2). Apache 2.0, RustVMM + KVM. |
| **RuntimeClass `cube`** | K8s RuntimeClass registered against CubeShim. Pods with `runtimeClassName: cube` schedule onto KVM-capable nodes and run inside CubeSandbox directly. |
| **CubeShim binary on each Cube-capable node** | The containerd Shim v2 handler that makes RuntimeClass `cube` work. |

**Services**:

| Service | Purpose |
|---|---|
| **mcp-registry** | Catalog of all available MCP tools. Each tool has a manifest (`shared/proto/mcp/<tool>.json`). Workloads query the registry to discover what they can use; admin workflows publish new tools. |
| **mcp-sandbox-runner** | The entry point for tool invocations. Validates the call against the tool manifest, allocates a CubeSandbox instance via the E2B SDK, executes, captures output, reaps the sandbox, returns the result. |
| **a2a-adapter** | Inter-agent communication. Publishes Agent Cards at `/.well-known/agent.json`, accepts JSON-RPC 2.0 task requests, translates them into internal envelopes, and exposes outbound A2A clients to L3 services. |

**Reference tool implementations** (under `tools/`):

| Tool | Purpose |
|---|---|
| `web-search` | Search the web via configured provider (e.g., Tavily, Brave Search). |
| `doc-search` | Semantic search over the workload's Qdrant collection via memory-svc. |
| `code-exec` | Execute arbitrary code inside the sandbox. The single most-used tool; the entire CubeSandbox bet pays off here. |

## Contracts

### Tool invocation (the L3 → L5 contract)

`mcp-sandbox-runner` exposes `POST /tools/invoke` with payload:

```json
{
  "tool_id": "code-exec",
  "tool_version": "1.2.0",
  "session_id": "...",
  "workload_app": "...",
  "input": { "...tool-specific..." },
  "deadline_ms": 30000,
  "idempotency_key": "uuidv7"
}
```

The runner:

1. Looks up the manifest via `mcp-registry`.
2. Validates input against the manifest's JSON Schema.
3. Checks the workload's tool allowlist (HasPermission against the Agent CRD).
4. Allocates a CubeSandbox via the E2B SDK (`E2B_API_URL` points at CubeMaster).
5. Executes; captures stdout, stderr, files, exit code.
6. Reaps the sandbox.
7. Returns the result envelope, including handles to any persisted artifacts.

### A2A inbound (peer agents calling our workloads)

- `a2a-adapter` publishes `/.well-known/agent.json` per workload, generated from kagent Agent CRD fields.
- Inbound: `POST /a2a/tasks` (JSON-RPC 2.0) with optional `Accept: text/event-stream` for streaming responses.
- Authentication: A2A peers present JWT issued by an allowlisted issuer. The peer's identity is logged for audit.

### A2A outbound (our workloads calling peers)

- L3 services use an internal `A2AClient` that goes through `a2a-adapter` for governance and telemetry uniformity.

### Downstream contracts

- CubeMaster Service at `cube-master.cube-system:8080` (E2B-compatible).
- `mcp-registry` Postgres-backed catalog (read-mostly).
- OTLP to `otel-collector.ai-observability:4317`.

## Distributed-system properties (L5 commitments)

- **Zero state in the sandbox**: every tool call runs in a fresh microVM. Persistence is via explicit artifact handles passed back to L4.
- **Egress policy** on sandbox networking is enforced by CubeVS via eBPF. Default-deny; tools that need network access declare it in their manifest and the runner whitelists per-call.
- **Time budget**: every tool call has a deadline; the runner kills the sandbox at the deadline and returns a timeout error.
- **Resource budget**: every tool call carries CPU and memory limits in the manifest; the runner enforces them.
- **Audit**: every invocation emits an `audit.tool.<tool_id>` event containing tool id, workload app, session id, input hash, output hash, duration, status. ClickHouse retains this for 90 days.
- **Idempotency**: the runner stores `(idempotency_key, result_hash)` in Redis with TTL > deadline; duplicate calls return the cached result.

## Service-level objectives

| SLO | Target |
|---|---|
| Sandbox cold start p99 | < 200 ms (CubeSandbox published P99 137 ms at 50 concurrent) |
| `mcp-sandbox-runner` end-to-end p99 (excluding tool work) | < 300 ms |
| Sandbox reap latency p99 | < 100 ms |
| A2A inbound task accept-to-ack p99 | < 200 ms |

## Out of scope

- Reasoning about which tool to call. The agent decides; the runner executes.
- LLM provider choice. Belongs to L1 (`ai-proxy-advanced`).
- Long-term memory. Belongs to L4.
- Telemetry storage. Belongs to L7.

## See also

- ADR-0005: CubeSandbox as the tool execution sandbox.
- ADR-0009: RuntimeClass cube for sandboxed pod execution.
- ADR-0003: MCP and A2A as the platform protocols.
- `FLOW.mmd` — tool invocation flow through the runner into CubeSandbox.
- `components.md` — manifest schema; CubeSandbox topology; A2A endpoint shape.
- `runbook.md` — provision CubeSandbox cluster, debug a stuck sandbox, rotate sandbox templates.

## Status

Documentation contract in place at Stage 00. CubeSandbox cluster lands at Stage 09. mcp-registry and mcp-sandbox-runner land at Stage 09. a2a-adapter lands at Stage 10.
