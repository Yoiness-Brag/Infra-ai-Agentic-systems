# agent-backend

Production-grade FastAPI service for the infra-ai MVP. It **owns auth, sessions and
session memory** and **delegates LLM/tool reasoning** to a kagent `Agent` over **A2A**
(JSON-RPC 2.0). It is the north-south backend behind Kong AI Gateway.

## How it works

```
Client ──Bearer JWT──▶ Kong (jwt plugin, 401 on bad token) ──▶ agent-backend
  POST /chat:
    1. re-verify JWT (HS256, iss=mvp-app, exp)          [auth.py]   defense-in-depth
    2. upsert session row in Postgres                   [sessions.py]
    3. memory.search(group_id=session_id) for context   [memory.py] Graphiti/FalkorDB
    4. A2A message/send → kagent Agent (Gemini + MCP)    [a2a_client.py] retry+breaker
    5. add_episode(user) + add_episode(assistant)        [memory.py]
    6. stream the answer back as SSE                     [main.py]
```

Endpoints:

| Method | Path       | Auth | Purpose |
|--------|------------|------|---------|
| POST   | `/chat`    | yes  | `{session_id?, message}` → SSE (`session`, `message`, `done` events) |
| GET    | `/healthz` | no   | Liveness (process up) |
| GET    | `/readyz`  | no   | Readiness: Postgres + FalkorDB + kagent A2A breaker |
| GET    | `/metrics` | no   | Prometheus exposition |

## Fail-closed secrets

`app/config.py` raises on startup if `JWT_SECRET`, `POSTGRES_PASSWORD` or
`GOOGLE_API_KEY` is empty or a known placeholder (`postgres`, `password`, …).
The container never boots with insecure defaults (REF-03/04 lesson).

## Environment variables

Required (no usable default — fail-closed):

| Var | Source secret (SPEC §6) | Meaning |
|-----|--------------------------|---------|
| `JWT_SECRET` | `jwt-secret` | HS256 shared secret (matches Kong jwt consumer) |
| `POSTGRES_USER` | `postgres-creds` | DB user (`agent`) |
| `POSTGRES_PASSWORD` | `postgres-creds` | DB password |
| `GOOGLE_API_KEY` | `gemini-api` | Gemini key for Graphiti LLM + embedder |
| `KAGENT_AGENT_A2A_URL` | (env, from kagent component) | kagent Agent A2A endpoint URL |

Optional / defaulted:

| Var | Default | Meaning |
|-----|---------|---------|
| `JWT_ISS` | `mvp-app` | Expected JWT issuer |
| `JWT_ALGORITHM` | `HS256` | JWT signing alg |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `postgres.ai-platform` / `5432` | |
| `POSTGRES_DB` | `agentmvp` | |
| `FALKORDB_HOST` / `FALKORDB_PORT` | `falkordb.ai-platform` / `6379` | |
| `FALKORDB_PASSWORD` | `""` | Optional (SPEC §6) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Graphiti LLM model |
| `GEMINI_EMBEDDING_MODEL` | `embedding-001` | Graphiti embedder |
| `A2A_TIMEOUT_SECONDS` | `60` | Per-call A2A timeout |
| `A2A_MAX_RETRIES` | `2` | Retries on transient A2A failure |
| `A2A_BREAKER_THRESHOLD` | `5` | Consecutive failures before breaker opens |
| `A2A_BREAKER_COOLDOWN_SECONDS` | `30` | Breaker cooldown before probe |
| `X_WORKLOAD_APP` | `mvp-app` | Per-app partition label written to sessions |
| `LOG_LEVEL` | `INFO` | Structured (JSON) log level |

## The `KAGENT_AGENT_A2A_URL` contract

This service is **only the A2A client** — another component (the kagent Agent
manifests) owns the endpoint. The expected shape (kagent v1alpha2) is:

```
http://<kagent-host>:8083/api/a2a/<namespace>/<agent-name>/
```

For this MVP the default in `k8s/deployment.yaml` is:

```
http://kagent-controller.kagent:8083/api/a2a/kagent/mvp-agent/
```

The kagent owner must confirm the controller Service name/port and the Agent
name (`mvp-agent`); override the env value if they differ. The client posts
JSON-RPC `message/send` and reuses `session_id` as the A2A `contextId`.

## Local dev

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
# (requires reachable Postgres + FalkorDB + kagent Agent, or override hosts)
```

## Build & deploy

```bash
docker build -t mvp/agent-backend:dev .         # multi-stage, non-root
kubectl apply -k k8s/                            # or via ArgoCD (SPEC §12)
```

Runs non-root (uid 10001), read-only rootfs, all caps dropped. Ingress only from
Kong + Prometheus; egress only to Postgres, FalkorDB, MCP servers, kagent A2A,
Kong, and DNS (see `k8s/networkpolicy.yaml`).
