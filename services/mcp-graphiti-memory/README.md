# mcp-graphiti-memory

FastMCP **STREAMABLE_HTTP** server wrapping **Graphiti-on-FalkorDB** (Gemini LLM
+ Gemini embedder) to give the kagent MVP agent per-session graph memory.

## Contract (per `infra-code/SPEC.md` §4, §9)

| Property | Value |
|---|---|
| Namespace | `ai-platform` |
| DNS:port | `mcp-graphiti-memory.ai-platform:3002` |
| MCP path | `/mcp` |
| Transport | `STREAMABLE_HTTP` |
| Image | `mvp/mcp-graphiti-memory:dev` |
| Backend | FalkorDB `falkordb.ai-platform:6379` |
| LLM / embedder | Gemini `gemini-2.5-flash` / `gemini-embedding-001` |

`group_id` partitions memory per session (SPEC §9: `group_id == session_id`).

## Tools exposed

```
memory_search(query: str, group_id: str) -> list[dict]
memory_add_episode(text: str, group_id: str, role: str = "user") -> str
```

- `memory_search` returns a list of `{"fact", "uuid", "valid_at",
  "source_node_uuid", "target_node_uuid"}` (facts from matching Graphiti
  `EntityEdge`s, scoped to `group_id`). Empty list if nothing matches.
- `memory_add_episode` stores a conversational episode and returns the stored
  episodic node UUID (string).

kagent `RemoteMCPServer.toolNames` must reference exactly:
`memory_search`, `memory_add_episode`.

## Fail-closed (SPEC §6)

The process **exits at startup** (`sys.exit(1)`) if `GOOGLE_API_KEY` is empty.
There are no default API-key fallbacks. The Deployment wires `GOOGLE_API_KEY`
from the `gemini-api` Secret with no default, so a missing/empty key crash-loops
the pod by design.

## Environment

| Var | Default | Source | Notes |
|---|---|---|---|
| `GOOGLE_API_KEY` | — (required) | `gemini-api` Secret | fail-closed if empty |
| `FALKORDB_HOST` | `falkordb.ai-platform` | env | |
| `FALKORDB_PORT` | `6379` | env | |
| `FALKORDB_PASSWORD` | _(none)_ | `falkordb-auth` Secret (optional) | optional per SPEC §6 |
| `GEMINI_LLM_MODEL` | `gemini-2.5-flash` | env | |
| `GEMINI_EMBED_MODEL` | `gemini-embedding-001` | env | |
| `SEARCH_NUM_RESULTS` | `10` | env | search result cap |
| `PORT` | `3002` | env | listen port |
| `LOG_LEVEL` | `INFO` | env | |

## NetworkPolicy

- Ingress: only from the `kagent` namespace on TCP 3002.
- Egress: DNS (53) + FalkorDB (6379, in-namespace pod `app=falkordb`) + Gemini
  API over HTTPS (443), with RFC1918 ranges excluded from the internet rule.

## Build / run locally

```bash
export GOOGLE_API_KEY=...          # required, or the server exits
export FALKORDB_HOST=localhost
pip install -e .
python server.py                   # serves http://0.0.0.0:3002/mcp
# docker build -t mvp/mcp-graphiti-memory:dev .
```
