# shared/proto/mcp/

MCP tool manifests. One JSON file per tool in the platform catalog. Loaded at startup by `mcp-registry`; manifest signatures are also consumed by `mcp-sandbox-runner` to enforce per-tool resource budgets, egress policy, and HITL gates.

```mermaid
flowchart LR
    FILES[mcp/{tool}.json] -->|load at startup| REG[L5 mcp-registry]
    REG -->|GET /manifests/{id}| MSR[L5 mcp-sandbox-runner]
    MSR -->|enforce schema + egress + timeout| CUBE[(CubeSandbox)]
```

## Files (one per platform-shipped tool)

- `web-search.json` — Tavily-backed web search (egress allowlist `api.tavily.com`).
- `doc-search.json` — Semantic doc search via `memory-svc` (no external egress).
- `code-exec.json` — Arbitrary code execution in CubeSandbox (`requires_approval: true` when egress is non-empty).

## Manifest schema

Every manifest validates against the MCP manifest JSON Schema and additionally carries platform-specific fields: `egress`, `timeout_ms`, `resources`, `requires_approval`. The validator lives in `mcp-registry/src/manifest_validator.py`.

## References

- MCP specification: https://modelcontextprotocol.io/
- Protocol note: `docs/protocols/mcp.md`.
- Layer specification: `docs/layers/L5-tooling-and-integration/README.md`.
- Each tool's own README: `tools/web-search/`, `tools/doc-search/`, `tools/code-exec/`.
