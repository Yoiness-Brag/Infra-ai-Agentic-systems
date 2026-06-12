# infra-code — MVP Spec & Build Contract

> Approved design 2026-06-12. A **production-grade MVP prototype** of a kagent-based agent on K3s.
> This file is the **single source of truth** every build component must conform to (namespaces,
> DNS, ports, image names, secrets, auth). Deviations from the platform docs are listed and are
> deliberate MVP scoping. Parent platform contract: repo `CLAUDE.md`, `.backlog/build-understanding.md`,
> `.backlog/k8s-requirements.md`.

## 1. Goal

Demonstrate, on a local **k3d** cluster managed by **ArgoCD**, a working agent that:
- is fronted by **Kong AI Gateway** (JWT auth + rate-limit + Gemini egress via `ai-proxy-advanced`),
- runs its reasoning on a **kagent `Agent`** (Gemini 2.5-flash) with **2 MCP tools** (web-search +
  graphiti-memory),
- is driven by a **FastAPI agent-backend** that owns auth, **session IDs in Postgres**, and
  **session memory as Graphiti episodes in FalkorDB**, delegating the loop to the kagent Agent over **A2A**,
- is observed by **Prometheus + Grafana**,
- has a **simple eval** (golden set + Gemini LLM-as-judge) and **CI** (build/scan/lint).

## 2. Request flow

```
Client ──Bearer JWT──▶ Kong (ai-gateway) ──HTTP/SSE──▶ agent-backend (ai-platform)
   agent-backend: re-verify JWT → upsert session (Postgres) → load memory (Graphiti/FalkorDB)
                → A2A call kagent Agent (kagent ns) → Agent loops Gemini + 2 MCP tools
                → write result episode (Graphiti) → stream SSE back
   kagent Agent's Gemini egress also routes through Kong ai-proxy-advanced.
   All pods expose /metrics → Prometheus (ai-observability) → Grafana.
```

## 3. Namespaces (create at stand-up)

`argocd` · `ai-gateway` (Kong) · `ai-platform` (falkordb, postgres, agent-backend, mcp-web-search,
mcp-graphiti-memory) · `kagent` (kagent controller, ModelConfig, Agent, RemoteMCPServer) ·
`ai-observability` (prometheus, grafana). Default-deny NetworkPolicy per ns + explicit allow edges.

## 4. Service DNS + ports (EXACT — do not deviate)

| Service | DNS:port | Notes |
|---|---|---|
| Kong proxy | `kong-proxy.ai-gateway:80` (k3d hostport 80→localhost:8080) | north-south entry |
| agent-backend (FastAPI) | `agent-backend.ai-platform:8000` | `/chat` (SSE), `/healthz`, `/readyz`, `/metrics` |
| mcp-web-search | `mcp-web-search.ai-platform:3001` path `/mcp` | MCP **STREAMABLE_HTTP** |
| mcp-graphiti-memory | `mcp-graphiti-memory.ai-platform:3002` path `/mcp` | MCP **STREAMABLE_HTTP** |
| FalkorDB | `falkordb.ai-platform:6379` | Graphiti backend (RESP) |
| Postgres | `postgres.ai-platform:5432` | db `agentmvp`, user `agent` |
| kagent Agent A2A | `kagent` ns (URL per kagent v1alpha2; confirm via context7) | FastAPI is the A2A client |
| Prometheus | `prometheus.ai-observability:9090` | scrapes `/metrics` |
| Grafana | `grafana.ai-observability:3000` | dashboards |

## 5. Images (built locally, imported into k3d — no external push needed for `mvp-up`)

`mvp/agent-backend:dev` · `mvp/mcp-web-search:dev` · `mvp/mcp-graphiti-memory:dev`. CI may also push to
GHCR with `${GITHUB_SHA::7}` tags (no `:latest`). Containers run **non-root**, read-only rootfs where possible.

## 6. Secrets (K8s Secret — names are contract; values via `.env` → `make` at stand-up, never committed)

| Secret (ns) | Keys | Used by |
|---|---|---|
| `gemini-api` (kagent, ai-platform) | `GOOGLE_API_KEY` | kagent ModelConfig + graphiti-memory MCP (Graphiti Gemini) |
| `jwt-secret` (ai-gateway, ai-platform) | `JWT_SECRET` (HS256 shared), `JWT_ISS=mvp-app` | Kong jwt consumer + agent-backend verify |
| `postgres-creds` (ai-platform) | `POSTGRES_USER=agent`, `POSTGRES_PASSWORD`, `POSTGRES_DB=agentmvp` | postgres + agent-backend |
| `falkordb-auth` (ai-platform) | `FALKORDB_PASSWORD` (optional) | falkordb + graphiti-memory MCP |

**Fail-closed (REF-03/04 lesson):** every service MUST refuse to start if its required secret is empty.
No `""`/`postgres`/default fallbacks.

## 7. Auth (high-attention)

- **Kong `jwt` plugin**: consumer `mvp-app`, HS256 credential (`key=mvp-app` = the `iss`, `secret=$JWT_SECRET`).
  Kong rejects missing/invalid JWT (401) before reaching the backend. Add OSS `rate-limiting` (per-consumer).
- **agent-backend re-verifies** the JWT (HS256, `iss=mvp-app`, exp) as defense-in-depth — never trusts
  Kong alone. Use `pyjwt`. 401 on failure.
- A dev helper `make token` mints a short-lived HS256 JWT for testing.

## 8. Gemini routing

kagent `ModelConfig` provider `Gemini`, model `gemini-2.5-flash`, key from `gemini-api`. **Egress through
Kong `ai-proxy`** (OSS; route `/llm/gemini` → Gemini upstream) to keep the gateway central
(ADR-0012; Enterprise `ai-proxy-advanced` not used — see §16). Graphiti (in the memory MCP) uses Gemini
embedder `gemini-embedding-001` directly (MVP deviation from self-hosted bge-large).

## 9. Memory & sessions

- **Postgres**: table `sessions(session_id uuid pk, app text, subject text, created_at, last_seen, meta jsonb)`.
  agent-backend upserts per request.
- **Graphiti-on-FalkorDB** (`graphiti-core[falkordb,google-genai]`): each turn → `add_episode` (user msg +
  agent result) partitioned by `group_id = session_id`; retrieval via `search`. Exposed through the
  **mcp-graphiti-memory** server (tools: `memory_search`, `memory_add_episode`); agent-backend may also call
  graphiti-core directly for session-lifecycle writes. One FalkorDB, `group_id` = session.

## 10. kagent objects (v1alpha2 — confirm shapes via context7 `/websites/kagent_dev` at build)

- Install: `helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent -n kagent` (+ CRDs chart).
- `ModelConfig` `gemini-model-config` (provider Gemini, model gemini-2.5-flash, apiKeySecret `gemini-api`).
- `RemoteMCPServer` ×2 → `mcp-web-search` and `mcp-graphiti-memory` (`protocol: STREAMABLE_HTTP`, the URLs in §4).
- `Agent` `mvp-agent` (`type: Declarative`): `systemMessage`, `modelConfig: gemini-model-config`,
  `tools: [{type: McpServer, mcpServer:{kind: RemoteMCPServer, name: <each>, toolNames:[...]}}]`,
  `a2aConfig.skills` (so FastAPI can reach it over A2A).

## 11. Observability (MVP)

Prometheus scrapes `/metrics` from agent-backend + both MCPs + Kong (`prometheus` plugin) + kagent.
Grafana with a Prometheus datasource + one dashboard `mvp-agent.json` (request rate, latency p50/p95,
error rate, Gemini token usage if exposed, MCP call count). **Deviation:** docs mandate Alloy→LGTM-P (ADR-0006).

## 12. GitOps & platform stand-up

- `platform/argocd/root.yaml` = App-of-Apps → `applications/*.yaml`, each → a path under `infra-code/`.
  Wave-0 stand-up (namespaces + default-deny NetworkPolicies + secret templates) lives in
  `platform/foundation/`.
  `repoURL` parameterized (default = this repo); sync-wave annotations order: foundation (wave 0) →
  data+kong+observability (wave 1) → kagent (wave 2) → mcp servers (wave 3) → agent + Agent CRD (wave 4).
- **`make mvp-up`**: create k3d → build+import 3 images → install ArgoCD → apply root app (GitOps path).
  **`make mvp-up-direct`**: same but `kustomize`/`helm` apply directly (no git needed) — guaranteed local run.
  `make mvp-down` deletes the k3d cluster. `make token` / `make smoke` for testing.

## 13. Eval (simple)

`eval/` : `golden.jsonl` (~8 Q/A incl. a memory-recall case + a web-search case), `run_eval.py` that hits
`/chat` with a JWT and scores answers with a **Gemini LLM-as-judge** on {correctness, faithfulness} (2 of the
5 platform metrics). Pass gate: ≥0.8 mean. Runnable locally + as a CI job (skips if no cluster).

## 14. CI

`.github/workflows/ci.yaml`: on PR touching `infra-code/**` → build the 3 images, **Trivy** scan,
`helm lint` + `kustomize build` + `kubeconform` manifests, ruff/mypy on Python. No deploy from CI (ArgoCD owns deploy).

## 15. Explicit deviations from platform docs (MVP scope, reversible)

Prometheus+Grafana not Alloy/LGTM-P (ADR-0006) · Gemini embedder not self-hosted bge-large (ADR-0004 RAG) ·
no Qdrant/rerank/NATS/KEDA/CubeSandbox/Langfuse/OPA · single-replica (no HA) · HS256 shared JWT (not per-app
RS256 issuers). Each is a known shortcut for the prototype; the full stack is the eventual target.

## 16. Build-time corrections (reconciled after the swarm build — these override §7/§8/§10 above)

- **Kong plugins are OSS, not Enterprise.** `ai-proxy-advanced` and `ai-rate-limiting-advanced` are Kong
  **Enterprise-only**. The MVP uses OSS **`ai-proxy`** (Gemini egress route `/llm/gemini`) and OSS
  **`rate-limiting`** (per-consumer request count) + **`jwt`** + **`prometheus`**. Token-aware AI rate
  limiting and multi-model routing are deferred (would need Enterprise or Kong's AI Gateway tier). This is
  a partial deviation from ADR-0012's `ai-proxy-advanced`, accepted for an OSS prototype.
- **kagent `Agent` v1alpha2 nests fields under `declarative:`.** The real shape is
  `spec.type: Declarative` + `spec.declarative.{modelConfig, systemMessage, tools[], a2aConfig}` (not flat
  under `spec` as sketched in §10). The committed `platform/kagent/agent.yaml` uses the correct nesting.
- **A2A method = `message/send`** (A2A v0.2+), not `tasks/send`. The kagent Agent is reachable at
  **`http://kagent-controller.kagent:8083/api/a2a/kagent/mvp-agent/`** (with trailing slash — the kagent
  controller serves `/api/a2a/{ns}/{agent}/`; Agent Card at `.../.well-known/agent.json`).
  agent-backend sets this as `KAGENT_AGENT_A2A_URL`. SSE `/chat` is single-shot (A2A send is non-streaming;
  token streaming would need `message/stream`).
- **Observability metric names** are app-prefixed: `agent_backend_requests_total`,
  `agent_backend_request_latency_seconds`, `agent_backend_a2a_calls_total{outcome}`. The Grafana dashboard
  queries these. The two MCP servers expose only `/mcp` (no `/metrics`) and are intentionally not scraped.
- **Versions to pin before deploy:** kagent chart patch (placeholder `0.6.21` → resolve via `helm show chart`),
  `graphiti-core` (`>=0.13`), `mcp` (`>=1.2`). FalkorDB `v4.2.2`, postgres `16.4`, prometheus `v2.54.1`,
  grafana `11.2.0`, Kong `3.9` are pinned.
- **ArgoCD GitOps needs the repo pushed/reachable** (`repoURL` default `github.com/YounssBrag/...`); for a
  pure-local run use **`make mvp-up-direct`** (no git dependency).

## 17. Review-pass hardening (2026-06-12 — 10x best-practice pass; overrides earlier values)

- **Banned wave-0 naming removed (platform terminology rule).** The wave-0 dir is `platform/foundation/`;
  the ArgoCD app is `00-foundation.yaml` (name `foundation`). The banned term no longer appears in `infra-code/`.
- **All `#` comments removed** from YAML/Dockerfiles/Makefile/Python (kept: shebangs, `# syntax=`/`# noqa`
  directives, concise docstrings, and `#` inside embedded scripts/prompt strings). Rationale lives here + READMEs.
- **Embedding model `embedding-001` → `gemini-embedding-001`** (legacy id retired by Google). Unified across
  agent-backend (`GEMINI_EMBEDDING_MODEL`) and mcp-graphiti-memory (`GEMINI_EMBED_MODEL`) so the shared graph
  stays consistent. Default output dim is 3072.
- **FalkorDB manifest fixes (would have crash-looped):** module path `/FalkorDB/bin/src/falkordb.so`, run as
  uid/gid **999** (image's `redis` user), and `--protected-mode no` (required for cross-pod RESP on the no-auth
  MVP path). Verified against the real `falkordb/falkordb:v4.2.2` image.
- **ArgoCD `v2.13` (EOL) → `v3.4.1`**, installed with `kubectl apply --server-side --force-conflicts` (CRDs
  exceed the client-side annotation limit). All Applications gained `syncPolicy.retry`; AppProject tightened to
  least-privilege `sourceRepos` + cluster-resource whitelist.
- **CI: Trivy action `0.28.0` → `0.36.0`** (the `0.28.0` tag was hit by the March-2026 trivy-action tag-hijack
  supply-chain incident; SHA-pinning recommended as a follow-up). Added `mypy` alongside `ruff`.
- **Resilience hardening** (no contract change): JWT verify pins `algorithms=["HS256"]` + leeway + `verify_aud=False`;
  asyncpg bounded pool + acquire timeout; A2A exponential backoff **with full jitter**; Graphiti ops wrapped in
  `asyncio.wait_for` timeouts + serialized lazy init; request-id correlation; `session_id` validated as UUID;
  ddgs context-manager bug fixed; `automountServiceAccountToken: false` + startup probes on pods; uv pinned `0.11.21`.
- **Open follow-ups:** kagent latest chart is `0.9.5` (v1alpha2 still current; `0.6.21` floor kept — resolve real
  patch via `helm show chart`); `.env.example` is permission-blocked from tooling — its single
  banned-term reference + comments must be cleaned manually.

## 18. Complete deviation ledger + corrections (2026-06-12 production-readiness audit)

Full audit and the defect register live in `docs/PRODUCTION-READINESS.md`. This section closes the
disclosure gaps the audit found in §15 and corrects two inaccurate claims.

**Corrections to earlier sections:**
- §13 said the eval runs "as a CI job" — it does NOT; no eval job exists in `ci.yaml` (the eval is
  local-only via `make eval`). The judge metrics are `{correctness, faithfulness}`, which are NOT "2 of
  the 5 platform metrics" — the platform's five are `{hallucination, helpfulness, relevancy, conciseness,
  toxicity}`; `faithfulness` overlaps `hallucination`, `correctness` is additional.
- §16 SSE note stands: `/chat` returns a single-shot SSE envelope (work completes before the stream opens).

**Deviations not previously listed in §15 (all accepted for the MVP, mandatory at the noted stage):**
- No TLS / cert-manager; cleartext Bearer token at the k3d edge; no mTLS (Stage 03/14).
- Plain K8s Secrets: no encryption-at-rest, no External-Secrets/Vault/SOPS/Sealed-Secrets; secrets are
  imperative (`make secrets`), outside GitOps reconciliation (Stage 14).
- FalkorDB runs unauthenticated by default (`FALKORDB_PASSWORD` optional, `--protected-mode no`) (Stage 02).
- Grafana anonymous Viewer enabled; default admin; ingress unrestricted (local-only) (Stage 03).
- No OpenTelemetry distributed tracing, no `gen_ai.*` semconv, no Loki log aggregation, no LLM token/cost
  telemetry, no Mimir Ruler alerting, no SLOs (Stage 03/12).
- No CubeSandbox / `runtimeClassName: cube`; MCP tools run as plain pods (safe ONLY because no MVP tool
  executes untrusted code — do not reuse the pattern for a `code-exec`-class tool) (Stage 09).
- No MCP endpoint auth (NetworkPolicy is the only control; ingress is namespace-wide, not pod-scoped) (Stage 09).
- No prompt-injection / tool-poisoning handling on tool results (web_search and memory_search feed
  untrusted content into agent context); no perimeter `ai-prompt-guard` (Kong OSS) (Stage 11/12).
- No idempotency key on memory writes (no episode uuid, no Redis dedup) — not forward-compatible with the
  platform at-least-once + UUIDv7 invariant (Stage 08).
- No Argo Rollouts canary, no ArgoCD Image Updater; image-tag rule `^[a-f0-9]{7}$` not exercised (Stage 13).
- No four-tool eval harness (DeepEval/Promptfoo/Ragas/Inspect AI), no RAGAS gates, no red-team/injection
  eval, no online in-prod scoring, no regression detection; n=8 golden set (Stage 12).
- No SBOM, no cosign/SLSA signing, no secret-scanning, no SAST, no dependency lockfiles; CI actions and
  base images are tag-pinned, not SHA/digest-pinned (Stage 13).
- No schema-migration tooling (Alembic/Atlas); DDL via init ConfigMap + idempotent CREATE (Stage 07+).

**Applied in this audit pass (code/doc):** backend Graphiti ops now wrapped in `asyncio.wait_for` +
serialized init (`GRAPHITI_OP_TIMEOUT`, default 60s); `graphiti-core` floor bumped to `>=0.13`;
memory-MCP README embedding model corrected to `gemini-embedding-001`; this ledger.

## 19. Run-blocker fixes applied (2026-06-12 make-it-run pass + 15-agent verification)

All run-blockers from the readiness audit are now CLOSED (statically verified: 7/7 kustomize builds,
YAML valid, `make -n mvp-up-direct` parses). A live `make mvp-up-direct` + `make smoke` is the final proof
and requires a real `GOOGLE_API_KEY` + Docker/k3d.

- **D-01 kagent NetworkPolicy** — added `platform/kagent/networkpolicy.yaml` (ingress 8083 from ai-platform;
  egress to MCP 3001/3002, Kong 8000, 443/6443, DNS); wired into `mvp-up-direct` and the 20-kagent ArgoCD app.
- **D-02 NetworkPolicy selectors** — Kong->backend now `app.kubernetes.io/name: agent-backend`; backend->MCP
  now `app: mcp-web-search` / `app: mcp-graphiti-memory` (match the real pod labels).
- **D-03 / V-2 Kong secrets** — Gemini key uses the env vault `{vault://env/GOOGLE_API_KEY}` (the `ai-proxy`
  `param_value` field IS referenceable). The **jwt credential `secret` is NOT a referenceable field**, so it
  uses `${JWT_SECRET}` rendered by `envsubst` into the `kong-declarative` ConfigMap at `mvp-up-direct` time
  (the env vault would store the literal string and 401 every token). Requires `envsubst` (gettext) locally.
- **D-05 MCP writable /tmp** — both MCP deployments got `HOME=/tmp` + `XDG_CACHE_HOME=/tmp` + an `emptyDir`
  at `/tmp` (Gemini/graphiti caches write there under read-only rootfs).
- **V-1 agent-backend Gemini egress** — added `:443` egress to `agent-backend-egress` (memory.py calls the
  Gemini embedder directly; was blocked by default-deny).
- **V-3 Kong proxy install** — added `platform/kong/helmfile.yaml` (chart `kong/kong` 2.51.0); `mvp-up-direct`
  installs it; or `helm install kong kong/kong -n ai-gateway -f platform/kong/values.yaml`.
- **.env/.env.infra populated** with local dev secrets; only `GOOGLE_API_KEY` is blank (the single user input).

**Still GitOps-only gap (not a local-run blocker):** `mvp-up` (ArgoCD) does not install the kagent/Kong Helm
releases via an Application (they install via helmfile in `mvp-up-direct`); the local path is `mvp-up-direct`.
