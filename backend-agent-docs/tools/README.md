# tools/

MCP tool implementations executed inside CubeSandbox. Each tool is packaged as a sandbox template image referenced from its manifest in `shared/proto/mcp/`. The platform ships three reference tools; workload-specific tools live with the workload or are added here as the catalog grows.

```mermaid
flowchart LR
    MANIFEST[shared/proto/mcp/<br/>manifest JSON] -->|loaded at startup| REG[L5 mcp-registry]
    REG -->|lookup| MSR[L5 mcp-sandbox-runner]
    MSR -->|"runtime: cube-template:<image>"| CUBE[(CubeSandbox)]
    CUBE -->|spawn microVM| VM[Sandbox]
    VM --> TOOL{Tool image<br/>from tools/*/Dockerfile}
```

## Contents

| Tool | Purpose |
|---|---|
| `web-search/` | Public web search via Tavily. |
| `doc-search/` | Semantic search over the workload's Qdrant collection via `memory-svc /retrieve`. |
| `code-exec/` | Arbitrary code execution inside a fresh CubeSandbox microVM. |

## References

- MCP specification: https://modelcontextprotocol.io/
- Protocol note: `docs/protocols/mcp.md`.
- Layer specification: `docs/layers/L5-tooling-and-integration/README.md`.
- CubeSandbox: https://github.com/TencentCloud/CubeSandbox
