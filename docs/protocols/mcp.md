# MCP — Model Context Protocol

This document is the platform-specific implementation note for MCP. The protocol specification itself is at the Linux Foundation Agentic AI Foundation; this document covers how the platform consumes and exposes MCP.

## Role in the platform

MCP is the contract between an agent and a tool. The platform treats every tool — `web-search`, `doc-search`, `code-exec`, and any workload-specific tool — as an MCP server with a manifest. Agents (kagent Agent CRDs) reference MCP tools via `ToolServer` CRDs.

MCP traffic is handled at two points:

1. **Inside the cluster**: `mcp-registry` catalogs MCP tools. `mcp-sandbox-runner` invokes them inside CubeSandbox microVMs.
2. **At the perimeter (when relevant)**: Kong's MCP plugin can route MCP traffic in or out of the cluster with OpenTelemetry semconv applied.

## Manifest contract

Every MCP tool the platform exposes ships a manifest under `shared/proto/mcp/<tool_id>.json`. Required fields:

| Field | Purpose |
|---|---|
| `name` | Unique tool id. |
| `version` | Semantic version. |
| `description` | One-paragraph description used by the LLM to decide when to call the tool. |
| `input_schema` | JSON Schema for the tool input. Validated by `mcp-sandbox-runner` on every call. |
| `output_schema` | JSON Schema for the tool output. |
| `runtime` | Sandbox template id (CubeSandbox template). |
| `resources` | CPU and memory budget per call. |
| `egress` | Network egress policy: `none`, `allowlist:[domains]`, or `unrestricted` (the last is forbidden by OPA in workload namespaces). |
| `timeout_ms` | Maximum runtime per call. |
| `requires_approval` | Boolean; when true, triggers an HITL gate. |

## kagent integration

A kagent Agent CRD references one or more ToolServer CRDs. Each ToolServer points at the MCP catalog entry. The Agent CRD's `toolAllowlist` further constrains which tools the agent may use, even if the ToolServer exposes more.

```yaml
# Example Agent CRD fragment
spec:
  toolServers:
    - name: platform-default
      ref: toolserver/default
  toolAllowlist:
    - web-search
    - doc-search
```

`mcp-sandbox-runner` re-checks the allowlist on every invocation. The ToolServer is a discovery surface; the Agent CRD is the policy surface.

## Kong MCP plugin

Kong AI Gateway includes MCP plugin support in 2026. The platform uses it for two cases:

1. **External MCP servers**: a workload that wants to expose its tools to peers outside the cluster routes them through Kong, which applies authentication, rate limiting, and OpenTelemetry semconv consistently.
2. **External tool sources**: when an agent inside the platform calls an MCP server outside the cluster, traffic flows through Kong egress so the same governance applies.

Internal cluster traffic (agent in namespace A calls runner in `ai-platform`) does not go through Kong; it uses native K8s Service-to-Service calls.

## Telemetry conventions

MCP tool calls emit OTel spans named `mcp.tool.invoke` with attributes:

- `mcp.tool.id`
- `mcp.tool.version`
- `mcp.tool.workload_app`
- `mcp.tool.exit_code`
- `mcp.tool.duration_ms`
- `gen_ai.usage.input_tokens` (if the tool itself made LLM calls)
- `gen_ai.usage.output_tokens`

Plus the standard `service.name`, `service.namespace`, and `trace_id` from OTel.

## See also

- ADR-0003: MCP and A2A as the platform's two protocol standards.
- ADR-0005: CubeSandbox as the tool execution sandbox.
- `docs/layers/L5-tooling-and-integration/README.md` — the L5 surface where MCP is implemented.
- `shared/proto/mcp/` — the manifest catalog.

## References

- Kong AI Gateway MCP docs: https://developer.konghq.com/ai-gateway/
- kagent ToolServer CRD: https://github.com/kagent-dev/kagent
