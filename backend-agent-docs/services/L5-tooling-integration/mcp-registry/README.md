# mcp-registry

The platform's only MCP tool catalog. Reads manifest files at startup and serves them via HTTP for runtime lookup by `mcp-sandbox-runner` and agents.

## Responsibilities

- Load tool manifests from `shared/proto/mcp/` at startup.
- Serve `GET /manifests/{tool_id}@{version}` for the runner to look up signatures and resource budgets.
- Serve `GET /tools` for agents to discover what they can call (subject to `Agent.spec.toolAllowlist`).
- Validate every manifest at load time against the MCP manifest JSON Schema.

## One registry

We do not maintain a parallel "user-defined tool registry" alongside this one. All tools land here.

## Install and setup

```bash
# Local dev
cd services/L5-tooling-integration/mcp-registry
uv sync
uv run uvicorn src.main:app

# In-cluster (Stage 09)
helm upgrade --install mcp-registry ./k8s/helm \
  --namespace ai-platform \
  --values k8s/helm/values.yaml
```

## Flow

```mermaid
flowchart LR
    PROTO[shared/proto/mcp/*.json] -->|loaded at startup| REG[mcp-registry]
    AGENT[agent-worker] -->|GET /tools| REG
    REG -->|filtered by Agent.spec.toolAllowlist| AGENT
    MSR[mcp-sandbox-runner] -->|GET /manifests/{id}| REG
    REG -->|manifest JSON| MSR
    REG -.->|OTLP| ALLOY[Grafana Alloy]
```

## References

- MCP specification: https://modelcontextprotocol.io/
- Manifest schemas: `shared/proto/mcp/`
- Protocol note: `docs/protocols/mcp.md`
- Layer specification: `docs/layers/L5-tooling-and-integration/README.md`

## Status

Service code lands at Stage 09.
