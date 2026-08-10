# platform/kagent — kagent control plane + MVP Agent (v1alpha2)

This directory is the **kagent platform layer** for the MVP. It installs the
kagent control plane and declares the MVP `Agent` (`mvp-agent`), its Gemini
`ModelConfig`, and the two MCP tool servers it consumes.

All CRs use `apiVersion: kagent.dev/v1alpha2` (confirmed via context7
`/websites/kagent_dev`).

## Files

| File | Resource | Summary |
|---|---|---|
| `install.md` | — | Install runbook (charts, versions, secret wiring, verify). |
| `helmfile.yaml` | — | Declarative install of `kagent-crds` + `kagent` charts. |
| `values.yaml` | — | Helm values: Gemini default provider; key injected at install from `gemini-api`. |
| `model-config.yaml` | `ModelConfig/gemini-model-config` | Gemini `gemini-2.5-flash`; key from Secret `gemini-api`/`GOOGLE_API_KEY`. |
| `remote-mcp-web-search.yaml` | `RemoteMCPServer/mcp-web-search` | `STREAMABLE_HTTP` → `http://mcp-web-search.ai-platform:3001/mcp`. |
| `remote-mcp-graphiti-memory.yaml` | `RemoteMCPServer/mcp-graphiti-memory` | `STREAMABLE_HTTP` → `http://mcp-graphiti-memory.ai-platform:3002/mcp`. |
| `agent.yaml` | `Agent/mvp-agent` | Declarative agent; Gemini + 2 MCP tools; A2A skills. |

## Tools wired into `mvp-agent`

| RemoteMCPServer | `toolNames` |
|---|---|
| `mcp-web-search` | `web_search` |
| `mcp-graphiti-memory` | `memory_search`, `memory_add_episode` |

All three CRs (`ModelConfig`, both `RemoteMCPServer`s, `Agent`) live in the
`kagent` namespace, so the Agent references the MCP servers in-namespace (no
`allowedNamespaces` needed).

## ⭐ A2A endpoint (CRITICAL cross-dependency)

The kagent controller exposes every `Agent` over **A2A** on the
**`kagent-controller`** service, port **`8083`**, at path
`/api/a2a/{namespace}/{agent-name}/`.

For `mvp-agent` in namespace `kagent`, the **in-cluster A2A endpoint** is:

```
http://kagent-controller.kagent:8083/api/a2a/kagent/mvp-agent
```

This is the exact value the **agent-backend** (FastAPI, in `ai-platform`) must
set as its `KAGENT_AGENT_A2A_URL` environment variable. It is the A2A client;
this is the A2A server it calls.

- A2A **base URL** (use this for `KAGENT_AGENT_A2A_URL`):
  `http://kagent-controller.kagent:8083/api/a2a/kagent/mvp-agent`
- Agent Card (discovery) is served at:
  `http://kagent-controller.kagent:8083/api/a2a/kagent/mvp-agent/.well-known/agent.json`

> An A2A client typically appends `/.well-known/agent.json` to the base URL to
> fetch the Agent Card, then POSTs JSON-RPC tasks to the same base. If the
> backend's A2A client library expects a trailing slash, use
> `…/api/a2a/kagent/mvp-agent/`.

Local smoke check:

```bash
kubectl -n kagent port-forward svc/kagent-controller 8083:8083
curl localhost:8083/api/a2a/kagent/mvp-agent/.well-known/agent.json
```

## Gemini egress

Per SPEC §8, Gemini calls should egress through Kong `ai-proxy-advanced`. That
route lives in the gateway layer; this directory only declares the `ModelConfig`
that names the provider/model and the `gemini-api` Secret.

## Field-verification notes (v1alpha2)

Verified against `/websites/kagent_dev`:

- `ModelConfig.spec`: `provider: Gemini`, `model`, `apiKeySecret`,
  `apiKeySecretKey`, `gemini: {}` — **confirmed**.
- `RemoteMCPServer.spec`: `protocol` (`STREAMABLE_HTTP` is the default), `url`,
  `description` — **confirmed**.
- `Agent.spec`: `type: Declarative` with a `declarative:` block containing
  `modelConfig`, `systemMessage`, `tools[].mcpServer{kind,name,toolNames}`, and
  `a2aConfig.skills[]` — **confirmed**. (NOTE: SPEC §10 shows the older *flat*
  shape with `systemMessage`/`tools` directly under `spec`; v1alpha2 nests them
  under `spec.declarative`, which is what these manifests use.)
- A2A endpoint pattern `kagent-controller:8083/api/a2a/{ns}/{name}/` —
  **confirmed** from the kagent A2A examples.

Unverified / assumptions to flag:
- **Tool names** (`web_search`, `memory_search`, `memory_add_episode`) are the
  contract names from SPEC §9/§10; they must match the tool names the MCP
  servers actually advertise. Verify with the running servers
  (`tools/list`) once the MCP layer is up.
- **Exact chart patch version** (`0.6.21`) is a placeholder on the confirmed
  v0.6 line — pin to the real published patch at install (see `install.md`).
- `a2aConfig.skills[].inputModes/outputModes` are included per the documented
  `AgentSkill` examples; they are optional in those examples.
