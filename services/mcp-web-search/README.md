# mcp-web-search

FastMCP **STREAMABLE_HTTP** server exposing a single web-search tool for the
kagent MVP agent. No API key required (DuckDuckGo).

## Contract (per `infra-code/SPEC.md` §4)

| Property | Value |
|---|---|
| Namespace | `ai-platform` |
| DNS:port | `mcp-web-search.ai-platform:3001` |
| MCP path | `/mcp` |
| Transport | `STREAMABLE_HTTP` |
| Image | `mvp/mcp-web-search:dev` |

## Tool exposed

```
web_search(query: str, max_results: int = 5) -> list[dict]
```

Returns a list of `{"title": str, "url": str, "snippet": str}` objects.
`max_results` is clamped to `[1, 20]`. On error it returns `[]`.

kagent `RemoteMCPServer.toolNames` must reference exactly: `web_search`.

## Implementation notes

- Built on the official MCP Python SDK (`mcp.server.fastmcp.FastMCP`) running
  `transport="streamable-http"`, `stateless_http=True`, `json_response=True`,
  bound to `0.0.0.0:3001` at path `/mcp`.
- Primary search backend: `ddgs` (DuckDuckGo). If `ddgs` import/call fails at
  runtime, it falls back to an `httpx` fetch of DuckDuckGo's HTML endpoint with
  stdlib regex parsing.
- No secrets required; this service has **no** fail-closed gate.

## Environment

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `3001` | Listen port |
| `LOG_LEVEL` | `INFO` | Logging level |

## NetworkPolicy

- Ingress: only from the `kagent` namespace on TCP 3001.
- Egress: DNS (53) + internet HTTPS/HTTP (443/80), with RFC1918 ranges excluded
  so the tool cannot reach cluster-internal services.

## Build / run locally

```bash
# requires uv or pip
pip install -e .
python server.py            # serves http://0.0.0.0:3001/mcp
# docker build -t mvp/mcp-web-search:dev .
```
