# End-to-End Finalization Register — infra-code L1..L7

Produced 2026-08-09 by a 7-agent read-only review swarm over `infra-code/` (52 YAML, 12 Python),
`docs/`, `platform/`, `backend-agent-docs/`, `evals/`. Every finding carries file:line. Nothing was
edited during the review pass.

Source reviews: foundation+data, gateway+scaling, observability, gitops+ci, backend-app,
platform-docs requirements, backend-agent+eval requirements, plus a Loki/Alloy/exporter research pass.

---

## 0. Host budget — the binding constraint

| Resource | Measured | Note |
|---|---|---|
| CPU | 16 vCPU (i7-11800H) | Not a constraint |
| RAM | **15,685 MiB total / ~6,970 MiB available** | **Binding** |
| Swap | **0 B** | Overcommit ends in host OOM-kill, not pod eviction |
| Disk | 64 GiB free (86% used) | Tight for image pulls |

Declared pod memory *limits* in the repo today already sum to **5,632 MiB** = 81% of free RAM,
before ArgoCD (~800-1,400 MiB) and kagent (unbounded, no `resources:` anywhere) are counted.

**No pod in the repo is Guaranteed QoS** — every one has `requests.memory < limits.memory`, so
kubelet eviction ranks Postgres and FalkorDB *first* (largest req→limit gap). This is the single
most consequential sizing defect.

### Missing tooling (nothing can run today)
`k3d`, `helm`, `kustomize` (standalone), `argocd`, `yq`, `helmfile`, `envsubst`(verify), `kubeconform`.
Present: `kubectl` v1.36.2 (bundled kustomize v5.8.1), `docker` 29.5.2, `git`, `gh`, `uv`, `jq`, `python3`.

---

## 1. P0 — the system cannot start or serve a request

| ID | Area | file:line | Defect |
|---|---|---|---|
| **P0-01** | GitOps | repo root | **Repo has ZERO commits and NO git remote.** All 10 ArgoCD Applications point at `https://github.com/YounssBrag/Infra-ai-Agentic-systems.git` → **HTTP 404** (401 on `git-upload-pack`). ArgoCD repo-server cannot clone. `make mvp-up` yields 10 red Applications. |
| **P0-02** | GitOps | `platform/argocd/` | No ArgoCD **repository credential** Secret exists anywhere. A private repo never syncs. |
| **P0-03** | Edge | `platform/kong/values.yaml:42` + `cluster/k3d/k3d-config.yaml:17-20` | `proxy.type: ClusterIP` + traefik disabled ⇒ **nothing binds node port 80**. klipper never creates `svclb-*`. `curl localhost:8080` → connection refused. `make smoke` cannot pass. |
| **P0-04** | Edge | `platform/kong/values.yaml:20-35` | **`extraEnvVars` is not a key in the `kong/kong` chart.** Helm silently ignores it. `JWT_SECRET`/`GOOGLE_API_KEY` never reach the container ⇒ `{vault://env/GOOGLE_API_KEY}` resolves empty ⇒ every Gemini call 400s. Correct key is `customEnv`. |
| **P0-05** | Edge | `platform/kong/values.yaml:31-35` + `Makefile:57-62` | Kong mounts Secret `gemini-api` from ns `ai-gateway`; `make secrets` creates it only in `kagent` and `ai-platform`. Pod → `CreateContainerConfigError`. `SPEC.md:60` omits `ai-gateway` too. |
| **P0-06** | Edge | `platform/kong/kong.yaml:15-18`, `k8s/kong-config-configmap.yaml:23-26` | Route `chat` has `strip_path: true` against a service URL with no path ⇒ Kong proxies `POST /` upstream. FastAPI registers only `POST /chat` ⇒ **every gateway request 404s.** |
| **P0-07** | Edge | `kong.yaml:9`, `kong-config-configmap.yaml:18` | `secret: "${JWT_SECRET}"` is a literal in the committed ConfigMap. `Makefile:104` renders it with `envsubst`, but ArgoCD app `kong` has `selfHeal: true` and reverts it within seconds ⇒ every JWT 401s on the GitOps path. **Verified via context7: `jwt_secrets.secret` is `encrypted`, NOT `referenceable` — the env-vault form cannot work here** (`platform/kong/README.md:69-76` is wrong). |
| **P0-08** | GitOps | `platform/argocd/applications/*` | **D-04 still open.** No Application has `source.chart`. kagent and Kong are Helm releases installed only by `mvp-up-direct`. Under `make mvp-up`, wave 2 applies `kagent.dev/v1alpha2` CRs with no CRDs and no controller ⇒ waves 2-4 never go Healthy. |
| **P0-09** | Cluster | `cluster/k3d/k3d-config.yaml` (no `options.runtime`) | **No memory cap on the k3d node container.** Kubelet advertises 15 GiB allocatable against ~6.9 GiB free. Scheduler over-admits; the **host** OOM killer arbitrates and can kill containerd or the k3s server itself. |
| **P0-10** | Data | `platform/data/falkordb.yaml:87,97` | Both probes run `redis-cli -a "${FALKORDB_PASSWORD:-}"`. On the documented no-password path this sends `AUTH ""`, the server replies `-ERR ... no password is set`, `cliConnect()` aborts **before PING** ⇒ readiness never true ⇒ liveness restart loop forever. |
| **P0-11** | Backend | `app/a2a_client.py:43-65,94-97` + `main.py:138-142` | Breaker deadlock. `is_open` is reset only by `record_success()`; `/readyz` fails on `is_open`. After 5 A2A failures: pod NotReady → removed from Service endpoints → no request reaches it → `record_success()` unreachable → **permanently NotReady** at `replicas: 1`. |
| **P0-12** | Backend | `main.py:170-175` + `sessions.py:30-37` | Session takeover → **cross-user memory leak**. `ON CONFLICT (session_id)` with no `subject` guard. User A submitting B's `session_id` reads B's Graphiti partition into A's prompt and writes A's turn into B's graph. (D-09, never fixed.) |
| **P0-13** | Agent | `platform/kagent/agent.yaml:20-24,43-50` | The Agent's `memory_search`/`memory_add_episode` take a **required** `group_id`, but nothing conveys the session id to the Agent — the backend passes it only as the A2A `contextId`, which kagent does not project into MCP tool args. The LLM must **invent** the partition key. |
| **P0-14** | Obs | `dashboards/mvp-agent.json:185-191` | Threshold steps inverted: `up == 1` (healthy) renders **RED**, `up == 0` renders **GREEN**. |
| **P0-15** | Obs | `platform/kagent/values.yaml` (4 lines, no `podAnnotations`) | Prometheus `kagent` job keeps on `prometheus.io/scrape=true`; kagent sets no annotations ⇒ **zero targets forever**. Control plane is a total blind spot. Three files disagree on the port (8080 / 8083 / 9090). |
| **P0-16** | CI | `.github/workflows/ci.yaml:33-41` | `push: false`, tag `mvp/<svc>:ci`. **CI never pushes to GHCR.** `permissions:` lacks `packages: write`; no `docker/login-action`. Images reach the cluster only via `k3d image import` from the laptop — the opposite of the requirement. |

## 2. P1 — breaks a documented intent or a real runtime path

Condensed; full text in the agent reports.

**Security / network**
- `platform/foundation/network-policies.yaml` — `argocd` ns (cluster-admin) has **no default-deny**; the only namespace with unrestricted egress.
- All four `allow-dns-egress` rules use `namespaceSelector: {}` ⇒ port 53 to **every pod in every namespace**.
- `services/agent-backend/k8s/networkpolicy.yaml:94-96` and `platform/kagent/networkpolicy.yaml:64-68` — bare `- ports:` with no `to:` ⇒ egress to `0.0.0.0/0` incl. pod CIDR and `169.254.0.0/16` metadata.
- `grafana.yaml:213-216,232-235` — ingress rules with no `from:` ⇒ any pod reads all dashboards and queries Prometheus (Grafana has anonymous Viewer on).
- `platform/kong/values.yaml:51-55` — unauthenticated in-cluster Admin API; `GET /consumers/mvp-app/jwt` returns the **HMAC secret in plaintext** (DB-less has no keyring).
- `platform/kong/values.yaml:73-80` — container-only fields (`readOnlyRootFilesystem`, `capabilities`, `allowPrivilegeEscalation`) placed in the **Pod**SecurityContext; the API server drops them. Correct key is `containerSecurityContext`. `seccompProfile` absent (D-12).
- All 4 `platform/foundation/secrets/*.example.yaml` use **non-empty** placeholders (`REPLACE_ME_FROM_ENV`) ⇒ fails **open**, violating SPEC §6 fail-closed.
- `cluster/k3d/k3d-config.yaml:11-15` — unauthenticated write-enabled registry bound to `0.0.0.0:5000`, and entirely unused.
- `Makefile:103-107` — plaintext JWT secret written to a fixed world-readable `/tmp/kong-rendered.yaml`; `rm -f` only on the success branch.

**Durability / data**
- `falkordb.yaml:66-77` — **no `--appendonly`, no `--save`** (D-08). Up to 1h loss window on the store designated as the memory graph *and* checkpoint store.
- `falkordb.yaml` — no `--maxmemory` vs a 1Gi limit ⇒ kernel SIGKILL instead of `OOM command not allowed`.
- `falkordb.yaml:70,76` — module loaded with no `THREAD_COUNT`; defaults to **16 host cores** against a 1-vCPU limit.
- `postgres.yaml:76-89` — no server tuning; `max_connections=100` × ~7 MiB ≈ 700 MiB inside a 1 GiB limit.
- Neither StatefulSet has a `startupProbe`, `automountServiceAccountToken: false`, `terminationGracePeriodSeconds`, or an explicit `storageClassName` — while all three app pods do.
- No k3d `volumes:` host bind ⇒ **all PVC data is destroyed by `make mvp-down`**, undocumented.

**Backend**
- `a2a_client.py:152-160` — retries and trips the breaker on **400/401/404**; one URL typo permanently bricks the pod (with P0-11).
- `a2a_client.py:181-214` — no `TaskState` handling. A **`failed` task's error text is returned to the user as the answer**.
- `a2a_client.py:108-109` — client-generated `contextId` (spec-discouraged); response `contextId` never read ⇒ no kagent-side multi-turn continuity.
- No Agent Card discovery. `SPEC.md:147` names `/.well-known/agent.json`, **renamed to `agent-card.json` in A2A v0.3.0**; latest spec is v1.0.1 which also **removed the `kind` discriminator** the client still sends.
- `main.py:184-208` — worst-case `/chat` ≈ **250 s** (A2A 60s×3 + 2×60s episode writes) vs Kong's default 60 s read timeout ⇒ gateway 504s while the turn is still persisted.
- `deployment.yaml:88-98` — `readOnlyRootFilesystem: true` with no writable `$HOME`; the same google-genai/graphiti stack that needed D-05 on the MCP pods. **`PRODUCTION-READINESS.md:50` tells the reader to "mirror agent-backend", which never had the fix.**
- `memory.py:47-55` — Gemini embedder calls bypass Kong entirely ⇒ no rate limit, no token metering, permanently invisible to AI metrics.
- No `uv.lock` in any service (`Dockerfile:13` glob matches nothing) ⇒ non-reproducible builds. No `tests/` anywhere; CI runs `ruff check services || true`.
- `main.py:98-108` — raw `request.url.path` as a Prometheus label ⇒ unbounded cardinality (and with P0-06 *every* request is currently a 404 on `/`).
- `metrics.py:13-17` — default histogram buckets top out at **10 s**; p95 panel is meaningless for LLM turns.

**GitOps / CI**
- `targetRevision: HEAD` in all 10 files — resolves to an unknown remote default branch (local is `master`, project main is `main`).
- `Namespace/ai-gateway` declared by **two** Applications, both `prune: true` + `selfHeal: true` ⇒ SharedResourceWarning and a prune can delete the namespace.
- Foundation app **owns `Namespace/argocd`** with prune ⇒ pruning it makes ArgoCD delete itself.
- `Makefile:100-122` — every apply is `|| true` ⇒ **`mvp-up-direct` always exits 0 even when nothing installed**. Verified: `helm`, `helmfile`, `k3d` absent, so today it "succeeds" with no gateway at all.
- **0 of 8 CI actions SHA-pinned** (D-07), including `aquasecurity/trivy-action@0.36.0` — the exact mutable-tag class `SPEC.md:174` cites as hijacked. Plus `curl .../install_kustomize.sh | bash` from `master`, unchecksummed.
- `AppProject.clusterResourceWhitelist` lacks `APIService`, `Validating/MutatingWebhookConfiguration`, `IngressClass` ⇒ **KEDA, cert-manager and Gatekeeper cannot sync**. `destinations` enumerates only 5 namespaces ⇒ any app targeting `minio`/`langfuse`/`loki`/`keda` is rejected.
- `project.yaml:8-9` — `resources-finalizer` on an **AppProject**; nothing removes it ⇒ `kubectl delete appproject` hangs forever.
- `prometheus.yaml:63-69` — static Service-DNS scrape ⇒ at replicas>1 each scrape hits a random pod and counters alias. **Corrupts every KEDA Prometheus query the instant autoscaling starts.**
- `ai-observability` has default-deny ingress with **no allow for Prometheus:9090** ⇒ already blocks Grafana→Prometheus today, and would block KEDA.
- `grafana.yaml:138` — `readOnlyRootFilesystem: true` but `GF_PATHS_LOGS=/var/log/grafana` is on the read-only root; needs `GF_LOG_MODE=console`.
- `Makefile:108` — `kubectl apply -f platform/observability` fallback bypasses Kustomize ⇒ `configMapGenerator` never runs ⇒ Grafana hangs in ContainerCreating on a missing dashboard ConfigMap.
- Images are 2 majors stale: `prom/prometheus:v2.54.1` (current **v3.13.2**), `grafana/grafana:11.2.0` (current **13.1.3**).

## 3. Verification of the previously-claimed fixes

`docs/PRODUCTION-READINESS.md` D-01..D-14 were reported closed. Actual: **6 fixed, 2 partial, 6 still open.**

| Fixed | Partial | **Still open** |
|---|---|---|
| D-01, D-05, D-06, D-11, D-13, D-14 | D-02, D-03 | **D-04, D-07, D-08, D-09, D-10, D-12** |

---

## 4. Gap register — required by the objectives, absent from the codebase

| # | Capability | State | Blocker |
|---|---|---|---|
| G-1 | **MinIO** PDF object store | 0% — no manifest, ns, PVC, Service, Secret, netpol, or ArgoCD app anywhere | Upstream `minio/minio` **archived 2026-04-25**, unpatched since 2025-09 → conflicts with the Trivy gate. Maintained AGPL fork `pgsty/silo` exists. **Set `CI_CD=true` or MinIO preallocates ≥1 GiB.** |
| G-2 | **PDF upload → chunk → FalkorDB graph** | 0% — no route, dep, parser, chunker, job, or limits | Cannot run inline: a 200-page PDF ≈ 400 sequential Gemini extraction calls. Needs a durable job ledger (`SELECT … FOR UPDATE SKIP LOCKED`) since NATS/Redis are out of scope. |
| G-3 | **LangGraph + FalkorDB checkpoints** | 0% | **Technically impossible off-the-shelf.** `langgraph-checkpoint-redis` requires **RedisJSON + RediSearch**; `falkordb/falkordb:v4.2.2` loads exactly one module (`falkordb.so`) and ships neither. `.setup()` fails on `FT.CREATE`. No LangGraph checkpointer exists for any graph DB. **Decision required.** |
| G-4 | **Langfuse self-hosted** | 0% | **ClickHouse is MANDATORY** — Langfuse docs: "there is no alternative OLAP database supported." v3 also hard-requires Redis/Valkey **and** S3/MinIO. Minimum tuned footprint ≈ **3.2 GiB**. Chart default is `clickhouse.replicaCount: 3` + `2xlarge` ≈ 9 GiB. **Conflicts with "we don't need clickhouse".** |
| G-5 | **Loki + log collector** | 0% | **Promtail EOL 2026-03-02**, code removed from Loki 3.7.3 → Alloy is the only supported option (ADR-0006 already locks it). Loki chart **moved to `grafana-community/helm-charts`** (2026-03-16); `SingleBinary` renamed `Monolithic` in chart 12.0.0. Default memcached subcharts request **multiple GiB** — must disable. |
| G-6 | **KEDA autoscaling** | 0% | CPU triggers are the wrong signal (LLM-latency-bound, low CPU). Needs a Prometheus concurrency trigger; **blocked by** the static scrape config (counter aliasing), the missing Prometheus ingress netpol, and ArgoCD `selfHeal` fighting the HPA over `/spec/replicas`. |
| G-7 | **LoadBalancer** | Broken | klipper is enabled but no `LoadBalancer` Service exists. One-line fix. |
| G-8 | **GHCR → ArgoCD pull** | 0% | No push, no `imagePullSecrets` anywhere, no Image Updater (`platform/argocd/image-updater-values.yaml` is referenced by README but **does not exist**). Tags are `:dev`/`:ci`, violating `^[a-f0-9]{7}$`. |
| G-9 | **ArgoCD UI + CLI** | Unreachable | No Ingress/NodePort/port-forward for `argocd-server`, **no ingress controller in the cluster** (traefik disabled, Kong IC disabled), no `server.insecure` patch, no admin-secret surfacing, `argocd` CLI never installed. |
| G-10 | **Swagger through Kong** | Unreachable | `/docs`, `/openapi.json`, `/redoc` are live in FastAPI but have **no Kong route**; and the `jwt` plugin is at **service** scope so `/docs` would 401 before loading. Swagger cannot render SSE — needs a `POST /chat/sync` variant. |
| G-11 | **OTel / `gen_ai.*` spans** | 0% | Zero OTel deps. Structural blocker: token counts exist **only at Kong's `ai-proxy`**, and `ai_metrics: true` emits nothing without `logging.log_statistics: true` on the ai-proxy plugin. |
| G-12 | **A2A completeness** | Partial | Client-only. No Agent Card served, no card discovery, no `Authorization` on the A2A call (any pod in `ai-platform` can drive the Agent). |

### Doc-mandated components deliberately OUT of the objective scope
NATS JetStream, Qdrant, Redis, rerank-svc, memory-svc/session-svc split, CubeSandbox + `RuntimeClass cube`, mcp-registry, mcp-sandbox-runner, OPA Gatekeeper, cert-manager, Mimir, Tempo, Pyroscope, eval-svc, Argo Rollouts, code-exec/doc-search tools. Of ~40 doc-mandated components, `infra-code/` implements 9.

---

## 5. Documentation state

- `.backlog/doc-contradictions.md` logged 37 findings. Re-verified: **DOC-11 is the only one closed. All 36 others are still present verbatim.**
- 5 new findings: **NEW-1 (P0)** `README.md:200`/`CLAUDE.md:61` cite **ADR-0006** as locking OPA Gatekeeper — ADR-0006 contains zero occurrences of "OPA"/"Gatekeeper"/"Kyverno"/"admission". The admission-policy choice is **unlocked**. **NEW-4 (P0)** four top-level trees the docs treat as canonical (`services/`, `shared/`, `tools/`, `.github/`) **do not exist** — every `shared/proto/...` path reference is dangling. **NEW-3** `Makefile:17` invokes `scripts/docs-check.sh`, which does not exist, so Stage 00's acceptance criterion cannot pass.
- Terminology bans: **1 "tenancy"** violation (`docs/adr/0007:20`), **10 "bootstrap"** violations (incl. `infra-code/.env.example:3`).
- Both `.env` files are permission-blocked from tooling — `SPEC.md:181-182` records the same block; the outstanding manual cleanup remains unverified.

---

## 6. Decisions required before any engineering action

1. **Langfuse vs ClickHouse** — Langfuse v3 cannot run without ClickHouse. Accept a 1-replica ClickHouse (~1.5 GiB), or drop Langfuse?
2. **LangGraph checkpoint backend** — FalkorDB is technically infeasible off-the-shelf. Postgres checkpointer / custom FalkorDB saver / add real Redis?
3. **Git + GHCR** — the GitHub repo does not exist. Create it and push, or run local-only (`mvp-up-direct`) with no GitOps?
4. **RAM strategy** — always-on lean profile with Langfuse on demand, or is more host RAM available?
