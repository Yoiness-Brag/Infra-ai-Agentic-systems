# CLAUDE.md — Infra-ai-Agentic-systems

Production-grade **AI infrastructure platform** for hosting agentic workloads on Kubernetes
(K3s only — k3d local, K3s-on-VM staging, K3s-on-EC2 AWS; **never EKS**). It is a deliberate
extension of the CNCF **kagent** project with Kong AI Gateway, CubeSandbox, Graphiti-on-FalkorDB
temporal memory, a multi-LLM router, and a Langfuse-integrated eval pipeline.

> This repo is the **platform**, not an agentic application. Workloads deploy onto it as standard
> K8s resources (kagent CRDs).
>
> **`production-grade-agentic/` is ONLY a reference agent-backend — it is NOT platform code and is
> out of scope right now.** It is fully gitignored. We will *modify it later* to build the actual
> agent, which will then be **deployed inside this infra-ai platform** as a kagent workload on K8s
> (Stage 07 ports/splits it into `agent-orchestrator` + `agent-worker`). Do not treat it as the
> product, do not build platform features from it, and do not prioritize fixing it now — its review
> findings (`.backlog/reference-port-review.md`) are deferred to the Stage-07 port.

**Status:** Stage 00 complete — full documentation contract, 12 accepted ADRs, 5 locked doctrines,
**0 service code written**. Next: Stage 01 (provision local k3d cluster + ArgoCD App-of-Apps).

---

## How to work in this repo

- **Read the docs before designing.** Canonical sources: `README.md`, `ARCHITECTURE.md`,
  `docs/adr/` (decisions are law), `docs/protocols/` (the 5 doctrines), `docs/layers/L1..L7`,
  `docs/stages/STAGE-00..14`. ADRs override everything else; if a doc disagrees with an ADR, the
  ADR wins and the doc is a bug (see `.backlog/`).
- **One stack per concern.** Maintaining a second backend for the same concern is the forbidden
  "duplicate-stack anti-pattern". Don't introduce alternatives "just in case".
- **Stages are sequential by dependency.** Don't build Stage N+1 infra before Stage N exists.
- **Folder discipline (CI-checked):** every folder carries `README.md` + `FLOW.mmd`, plus
  `runbook.md` / `components.md` where applicable. A reader landing in any subdir must orient
  without leaving it.
- **Schema-first.** Contracts live in `shared/proto/` (OpenAPI=HTTP, AsyncAPI=NATS, A2A Agent Card,
  MCP manifest). Pydantic models are the single source of truth; specs are generated/validated in CI.
- **ADRs are immutable.** Supersede, never edit. New irreversible decision → write a numbered ADR
  (use the `adr-writer` skill). Overriding an eval/RAGAS gate also requires an ADR.
- **Terminology bans:** don't write "tenancy" (use *per-app isolation / namespace boundary*) or
  "bootstrap" (use *cluster provisioning / platform stand-up*).

---

## Canonical stack (one-per-concern, ADR-locked)

| Concern | Locked choice | ADR |
|---|---|---|
| Cluster substrate | **K3s only** (k3d / VM / EC2) — no EKS, no kind, no kubeadm | 0010 |
| Repo topology | Single **monorepo**, in-repo GitOps target | 0001 |
| Navigation | **7-layer model** `L1`–`L7`; spanning feature → higher-numbered layer | 0002 |
| Protocols | **MCP** (tools) + **A2A** (inter-agent) only | 0003 |
| Base platform + runtime | **kagent**, **Python ADK runtime only** (no Go ADK) | 0011 |
| Gateway | **Kong AI Gateway** (OSS 3.8+) — kgateway uninstalled | 0012 |
| Message bus | **NATS JetStream** (R3) + **KEDA** — no Kafka/Pulsar/Redis Streams/Rabbit | 0007 |
| Graph memory | **Graphiti on FalkorDB** — no Neo4j/Mem0/Kuzu | 0004 |
| Vector store | **Qdrant** (hybrid dense+sparse, RRF) — no pgvector/Weaviate/Pinecone | 0004 |
| Embedding / Rerank | **`bge-large-en-v1.5`** / **`bge-reranker-v2-m3`**, self-hosted only | 0004 + RAG |
| Tool sandbox | **CubeSandbox** + `RuntimeClass cube` — no Kata/gVisor/E2B-Cloud | 0005 + 0009 |
| Telemetry collector | **Grafana Alloy** (unified) — no vanilla OTel Collector / kube-prometheus-stack / Promtail | 0006 |
| Backends | **LGTM-P** (Loki, Grafana, Tempo, Mimir, Pyroscope) + **Langfuse v3** | 0006 |
| Admission policy | **OPA Gatekeeper** — no Kyverno | 0006 |
| CI / CD | **GitHub Actions** + **ArgoCD** (App-of-Apps, Image Updater, Argo Rollouts) | 0008 |
| Short-term / checkpoints / audit / objects | Redis / Postgres (LangGraph) / ClickHouse / MinIO | — |

No service mesh (Istio/Linkerd). No Temporal/Airflow (LangGraph + orchestrator-worker only).

---

## Hard invariants (guardrails)

- Every async edge carries a **UUIDv7 idempotency key**; every consumer keeps a Redis dedup table
  (TTL > redelivery window). Delivery is at-least-once.
- **Circuit breaker on every external dependency** (LLM, FalkorDB, Qdrant, MCP tool).
- Liveness/readiness/startup probes per service; readiness flips false on dependency outage;
  graceful SIGTERM drain.
- **Reranking is mandatory**; hybrid search is the floor. RAGAS gates are **blocking**, not advisory:
  Faithfulness >0.90, Answer Relevancy >0.85, Context Precision >0.80, Context Recall >0.75.
- Agents **never** touch Qdrant/FalkorDB directly — only via `memory-svc` (NetworkPolicy-enforced).
- GenAI semconv (`gen_ai.*`) on all LLM spans. **No prompt/completion bodies in span attributes** —
  only in span events (32 KB cap, redactable at Alloy egress).
- Default-deny NetworkPolicies per namespace; default-deny sandbox egress.
- OPA Gatekeeper enforces: resource limits, no `:latest`, no privileged (except `cube-system`),
  `runtimeClassName: cube` in tool namespaces, default-deny NetworkPolicy.
- Image tags = `${GITHUB_SHA::7}` (`^[a-f0-9]{7}$`); `:latest` forbidden.
- **No `/v1/` URL prefixes** on internal APIs — contracts evolve via schema.
- Test gates: ≥80% unit line coverage; 100% public APIs have a contract test; every NATS subject has
  an AsyncAPI contract test.
- Per-app isolation = namespace + own JWT issuer + Postgres RLS id + NATS subject prefix +
  NetworkPolicies; memory partitioned by `X-Workload-App` (Graphiti group_id / Qdrant collection /
  Redis prefix / Postgres RLS).

---

## The 5 cross-cutting doctrines (`docs/protocols/`)

Doctrines evolve via PR; a contradicting design needs a written exception in the service README.

- **Context engineering** — Selection / Retrieval / Compression / Persistence of what enters the
  context window, governed by a 6-layer context budget (tunable via `Agent.spec.contextBudget`).
- **Heuristic engineering** — cost/latency/safety/reliability decisions lifted into deterministic,
  observable, testable rules; every heuristic emits a `heuristic.<name>` counter.
- **RAG architecture** — semantic chunk → hybrid dense+sparse → RRF (top-50) → cross-encoder rerank
  (top-K≈5) → RAGAS gates. All retrieval via `memory-svc`.
- **Harness engineering** — four-tool eval composition: DeepEval (app-unit) + Promptfoo (prompt/red-team)
  + Ragas (RAG) + Inspect AI (safety), plus 5 online LLM-as-judge metrics in `eval-svc`.
- **Testing strategy** — unit → integration (testcontainers) → contract (schemathesis/AsyncAPI) →
  load (locust) → chaos (toxiproxy) → E2E (staging gates prod).

---

## Build roadmap — 15 stages (`docs/stages/`)

`01` provisions, then `02/03/04/05` parallel; `06` needs `01,03,04,05`; `08,09,10` after `07`;
`14` after `13`.

| # | Stage | Goal | Layers |
|---|---|---|---|
| 00 | Foundation | Docs contract only (**done**) | all |
| 01 | Cluster provisioning | k3d + ArgoCD App-of-Apps; `make local-up/down` | platform |
| 02 | Data plane | Postgres, Qdrant, FalkorDB, Redis, ClickHouse, MinIO + backups | L4 |
| 03 | Observability | Alloy + LGTM-P + Langfuse v3 + cert-manager + OTTL redaction | L7 |
| 04 | Message bus | NATS JetStream (R3) + KEDA + AsyncAPI subjects | L2 |
| 05 | Gateway | Install Kong AI Gateway; uninstall kgateway | L1 |
| 06 | kagent base | kagent control plane (Python ADK); Kong-fronted LLM egress | L3 |
| 07 | Agent runtime | Port reference workload → `agent-orchestrator` + `agent-worker`; **mem0 removed** | L2/L3 |
| 08 | Memory | `memory-svc`/`session-svc`/`rerank-svc`; `POST /retrieve` | L4 |
| 09 | Tools + sandbox | CubeSandbox cluster + RuntimeClass + `mcp-registry`/`mcp-sandbox-runner` | L5 |
| 10 | A2A interop | `a2a-adapter`; Agent Cards from CRDs; JSON-RPC 2.0 | L5 |
| 11 | Governance | OPA constraints + ClickHouse audit ledger + OTTL enforcement | L6 |
| 12 | Evaluation | `eval-svc` 5 judges + four-tool CI harness + golden datasets | L7 |
| 13 | CI/CD GitOps | per-service CI + Image Updater + Argo Rollouts canary + Trivy | platform |
| 14 | AWS parity | Replicate on K3s-on-EC2 (identical manifests) | platform |

---

## Conventions

- **Layout:** `platform/` (Helm/manifests), `services/` (workload code), `tools/` (reference MCP
  tools), `shared/proto/` (schemas), `docs/`, `evals/`. Layer prefixes `L1-`…`L7-`.
- `agent-orchestrator`/`agent-worker` live under `services/L3-agent-runtime/` (their dispatch *role*
  is L2 but runtime instances are L3).
- Per-service `pyproject.toml` + `uv` lockfile (no shared lockfile). CI builds only changed paths.
- **NATS subjects:** `agents.subtask.<sid>`, `agents.result.<sid>`, `tools.invoke.<tool>.<sid>`,
  `memory.ingest.<app>`, `audit.<service>.<action>`.
- **Heuristic naming:** `<scope>-<verb>`; adding one requires metric + DeepEval test + catalog update.

## Build / dev commands

```bash
make local-up     # provision local k3d cluster + ArgoCD + sync platform (Stage 01+)
make verify       # health checks across all layers
make eval         # LLM-as-judge eval pipeline (Stage 12+)
make local-down   # tear down
# Reference port (production-grade-agentic/): uv-managed FastAPI app — see its README
```

---

## Reference port status (`production-grade-agentic/`)

Reviewed at **58/100** — clean layering, good LLM-resilience patterns, but it **does not boot as-is**.
Fix before/while porting in Stage 07 (full findings in `.backlog/reference-port-review.md`):

- **CRITICAL** — broken imports: `src/main.py:24` (`interface.api` → `interface.router`);
  `src/agent/tools/__init__.py:10` (`duckduckgo_search` → `web_search`).
- **CRITICAL** — `JWT_SECRET_KEY` defaults to `""` (`settings.py:162`); `POSTGRES_PASSWORD="postgres"`
  default (`settings.py:176`). Must fail closed.
- **HIGH** — wildcard CORS + credentials; swallowed `None` from `workflow.get_response`;
  fire-and-forget `asyncio.create_task` memory updates; password HTML-escaping breaks login for
  passwords with `<>&`. Stage 07 also **removes `mem0ai`** (replaced by memory-svc).

## Known doc contradictions to resolve (tracked in `.backlog/`)

A deep atomic file-by-file review (2026-06-02) logged **37 findings** in
`.backlog/doc-contradictions.md`. Highest priority:
- **P0 `DOC-12`** — `ARCHITECTURE.md:23,37` claims kagent is multi-runtime (Python **+ Go** ADK),
  contradicting ADR-0011 + README "**Python ADK only**". Fix ARCHITECTURE or supersede the ADR.
- **P1** — vanilla `otel-collector:4317`/`kube-prometheus-stack` vs Alloy (ADR-0006, `DOC-01/02`);
  pgvector banned but used (`DOC-13`); `tools.invoke.*` has no stream spec (`DOC-03`); CI references
  nonexistent `evals/{promptfoo,ragas-suites,inspect-suites}/` dirs (`DOC-17`); L3/L4 FLOW diagrams
  omit a2a-adapter / rerank-svc / `POST /retrieve` (`DOC-18/19`); `agentic-rag-trigger` heuristic
  missing from catalog (`DOC-04`); kagent CRD extension fields lack an ADR (`DOC-05`).

Always read `.backlog/` before editing docs so fixes aren't duplicated or re-litigated.

---

## Memory & coordination tooling

This project uses **three** memory layers (chosen 2026-06-02):
1. **ruflo** (`/usr/bin/ruflo`, v3.x) — primary cross-session memory + swarm coordination. DB at
   `.claude/memory.db` + `ruvector.db` (HNSW vector search, pattern learning). NOTE: `claude-flow`
   and `ruflo` are the **same project** — use one (`ruflo`), not both.
2. **Built-in Claude memory bank** — `MEMORY.md` index + `memory/` facts (project decisions).
3. **Engram** (external) — being set up; standalone memory service.

Also active: `claude-mem` plugin and `context-mode` knowledge base (session-scoped research index).

**Before a task:** `ruflo memory search -q "<keywords>"` (or `memory_search` MCP tool).
**After success:** `ruflo memory store -k "<name>" --value "<what worked>"`.
Full swarm/agent-coordination guidance: **`.claude/ruflo-coordination.md`** (SendMessage-first,
topology, agent routing, hooks). Use a swarm for 3+ file / cross-module work; not for single-file edits.
