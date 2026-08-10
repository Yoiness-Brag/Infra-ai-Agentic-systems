# mcp-sandbox-runner

The platform's tool execution entry point. Validates input against the tool manifest, checks the workload's tool allowlist, allocates a CubeSandbox via the E2B SDK, executes, captures output, reaps the sandbox, emits audit events.

## Responsibilities

- Validate input against the manifest schema (from `mcp-registry`).
- Enforce `Agent.spec.toolAllowlist` (defense-in-depth check, even though the agent already filtered).
- Allocate a sandbox via E2B SDK with `E2B_API_URL=http://cube-master.cube-system:8080`.
- Apply egress policy from the manifest to CubeVS.
- Enforce `tool-deadline` and resource budget.
- Cache idempotent results in Redis db=1.
- Emit `audit.tool.<tool_id>` event with input_hash, output_hash, duration, exit_code.

## One runner

Per ADR-0005 / ADR-0009 there is also a RuntimeClass-cube integration model for long-running sandboxed pods. The runner is the per-call path; the RuntimeClass is the per-pod path. They cover different use cases and do not duplicate.

## Install and setup

```bash
# Local dev
cd services/L5-tooling-integration/mcp-sandbox-runner
uv sync
uv run uvicorn src.main:app

# In-cluster (Stage 09)
helm upgrade --install mcp-sandbox-runner ./k8s/helm \
  --namespace ai-platform \
  --values k8s/helm/values.yaml
```

## Flow

```mermaid
flowchart LR
    AGENT[agent-worker] -->|POST /tools/invoke| MSR[mcp-sandbox-runner]
    MSR -->|GET /manifests/{id}| REG[mcp-registry]
    MSR -->|allowlist check| MSR
    MSR -->|idempotency check db=1| REDIS[(Redis)]
    MSR -->|"E2B SDK<br/>createSandbox + exec"| CM[CubeMaster]
    CM -->|schedule on KVM| CL[Cubelet]
    CL -->|spawn microVM| VM[Sandbox]
    VM -->|stdout/stderr/files/exit| MSR
    MSR -->|"reapSandbox"| CM
    MSR -->|"cache result"| REDIS
    MSR -->|"publish audit.tool.{id}"| NATS[NATS]
    MSR -->|result envelope| AGENT
    MSR -.->|OTLP| ALLOY[Grafana Alloy]
```

## References

- E2B Python SDK: https://github.com/e2b-dev/E2B
- CubeSandbox: https://github.com/TencentCloud/CubeSandbox
- MCP specification: https://modelcontextprotocol.io/
- Protocol note: `docs/protocols/mcp.md`
- Decision rationale: `docs/adr/0005-tool-sandbox-cubesandbox.md`
- Layer specification: `docs/layers/L5-tooling-and-integration/README.md`

## Status

Service code lands at Stage 09.
