# Build Understanding — what we are building

> Synthesized 2026-06-12 from a 5-agent deep comprehension read of all docs (overview+ADR, doctrines,
> layers, stages, infra). Comprehension reference, not a contradiction list (those live in
> `doc-contradictions.md`). Pair with `k8s-requirements.md` (deployment requirements).

## 1. Thesis (what this is)

A production-grade, **self-hosted AI infrastructure platform** that hosts agentic workloads on
**K3s** — a deliberate extension of CNCF **kagent**. It provides, as substrate (so each workload
never rebuilds them), the ~7 cross-cutting properties agentic systems need: governed entry +
multi-LLM egress (Kong), durable fan-out bus (NATS JetStream), a reasoning runtime (kagent Python ADK
+ LangGraph orchestrator/worker), a unified memory plane (`memory-svc` over Graphiti-FalkorDB +
Qdrant + Redis + Postgres), kernel-isolated tool sandboxing (CubeSandbox), a governance plane (OPA +
Kong guardrails + Alloy redaction + ClickHouse audit), and GenAI-native observability + eval (Alloy →
LGTM-P + Langfuse + `eval-svc`). **Workloads deploy as kagent CRDs** (`Agent`, `ToolServer`,
`ModelConfig`). The platform is the product — not the agent. One technology per concern; every choice
ADR-locked. `production-grade-agentic/` is **only a reference agent-backend** to validate the
platform (ported in Stage 07), not platform code.

## 2. The agentic runtime model (what a workload actually does)

Orchestrator-Worker on LangGraph (autonomous-agents lens): a **lead** (`agent-orchestrator`, FastAPI +
LangGraph + Postgres checkpointer) plans, fans subtasks out on `agents.subtask.<sid>` (NATS), parallel
**workers** (`agent-worker`, KEDA-scaled on consumer lag) execute (LLM via Kong, tools via L5, memory
via L4), return on `agents.result.<sid>`, and the lead reconciles + streams SSE back through Kong.
Reliability is engineered, not hoped: **durable checkpointing** (Postgres, resume mid-run — never
MemorySaver), **bounded autonomy** via the heuristic budgets (step ≤12, run ≤90s, tokens ≤50K, cost
≤$0.50, fan-out ≤8, confidence-escalation @0.6), **at-least-once + UUIDv7 idempotency + Redis dedup**,
**circuit breakers on every external dep**, and **HITL gates** that pause/resume on
`audit.hitl.<workload>`. These directly counter the autonomous-agent failure modes (compounding error,
context/cost blowup, fabrication, unsafe actions).

## 3. The 5 doctrines (how the platform thinks) → service requirements

- **Context engineering** — 6-layer token budget (system 8% / semantic-RAG 35% / operational-graph 12%
  / conversational 25% / tool-results 15% / tool-catalog 5%), tunable per workload via
  `Agent.spec.contextBudget`; 4 dimensions Selection/Retrieval/Compression/Persistence. Owners:
  `memory-svc` (Qdrant+Graphiti+Redis surfaces), `session-svc` (compaction @8K tokens / 24 turns),
  orchestrator (budget + LangGraph checkpointer), `mcp-registry` (tool catalog, descriptions only).
- **Heuristic engineering** — deterministic guardrails around the LLM, grouped: dispatch / model-routing
  / compaction / retrieval / tool-use / termination (budgets above). Every heuristic emits a
  `heuristic.<name>` counter **and** needs a DeepEval test; changing a default budget needs an ADR.
- **RAG architecture** — mandatory pipeline: semantic chunk → hybrid dense+sparse → **RRF top-50** →
  **cross-encoder rerank top-K≈5** → RAGAS gates. Embedding `bge-large-en-v1.5` (1024-dim), reranker
  `bge-reranker-v2-m3` (`rerank-svc`), both self-hosted. **Reranking mandatory; hybrid is the floor.**
  RAGAS **blocking** gates: Faithfulness >0.90, Answer Relevancy >0.85, Context Precision >0.80,
  Context Recall >0.75. **All retrieval via `memory-svc`** — agents never touch Qdrant/FalkorDB directly.
- **Harness engineering** — four tools, each owns a layer: **DeepEval** (app-unit, ≥90% pass),
  **Promptfoo** (prompt/red-team, ≤5% regression), **Ragas** (RAG thresholds), **Inspect AI** (safety,
  zero must-pass fails) + **5 online LLM-judge metrics** (hallucination, helpfulness, relevancy,
  conciseness, toxicity) run by `eval-svc` on live Langfuse traces. CI threshold miss blocks PR;
  override needs an ADR.
- **Testing strategy** — pyramid: unit → integration (testcontainers) → contract (schemathesis HTTP +
  AsyncAPI runner for every NATS subject) → load (locust) → chaos (toxiproxy) → E2E (staging gates
  prod). Gates: ≥80% unit line coverage, 100% public APIs have a contract test.

## 4. The 7 layers (what gets deployed, by responsibility)

| L | Name | Components (role) | Key contract |
|---|---|---|---|
| L1 | Interface/Entry | **Kong AI Gateway** (jwt, ai-rate-limiting-advanced, ai-semantic-cache, ai-proxy-advanced multi-LLM, ai-prompt-guard, request-transformer, prometheus, otel) | HTTPS+SSE in; LLM egress out; routes to L2 by path |
| L2 | Orchestration | **NATS JetStream** (R3), **KEDA** (scale on lag), **kagent controller** | east-west subjects `agents.subtask/result.<sid>`, `memory.ingest.<app>`, `audit.<svc>.<action>` |
| L3 | Agent Runtime | **Agent/ToolServer CRDs**, `agent-orchestrator`, `agent-worker`, `a2a-adapter` | `POST /chat/stream` (SSE); per-app namespace isolation |
| L4 | Context/Memory | **memory-svc**, **session-svc**, **rerank-svc**, + stores FalkorDB/Qdrant/Redis/Postgres | `/memory/*` API, headline `POST /retrieve` (hybrid→RRF→rerank); `X-Workload-App` partition |
| L5 | Tooling/Integration | **CubeSandbox** (CubeMaster/Cubelet/CubeProxy/CubeVS/CubeShim) + `RuntimeClass cube`, `mcp-registry`, `mcp-sandbox-runner`, `a2a-adapter`, ref tools (web-search/doc-search/code-exec) | `POST /tools/invoke`; A2A `/.well-known/agent.json` + JSON-RPC 2.0 |
| L6 | Safety/Governance | **OPA Gatekeeper**, **cert-manager**, OTTL redaction (runs in Alloy), ClickHouse `platform_audit` | admission constraints; 4 enforcement points; 90d audit |
| L7 | Observability/Eval | **Grafana Alloy** (R3, unified collector), **LGTM-P** (Loki/Grafana/Tempo/Mimir/Pyroscope), **Langfuse v3**, **eval-svc**, ClickHouse/MinIO | OTLP in; `gen_ai.*` semconv; bodies in span events only (32KB cap) |

`agent-orchestrator`/`agent-worker` code lives under `services/L3-agent-runtime/` though their dispatch
*role* is L2. Full component→layer→source index in the layer agent's brief and `k8s-requirements.md` §4.

## 5. Build roadmap (the 15 stages, in dependency order)

`00 → 01 → (02,03,04,05) → 06 → 07 → (08,09,10,11,12) → 13 → 14` (acyclic; topo-valid).

| # | Stage | One-line goal | Depends |
|---|---|---|---|
| 00 | Foundation | docs contract only (**done**) | — |
| 01 | Cluster provisioning | k3d + ArgoCD App-of-Apps; `make local-up/down` | 00 |
| 02 | Data plane | Postgres(CNPG)/Qdrant/FalkorDB/Redis + ClickHouse/MinIO + backups | 01 |
| 03 | Observability | Alloy + LGTM-P + Langfuse v3 + cert-manager + OTTL | 01 |
| 04 | Message bus | NATS JetStream R3 + KEDA + 4 AsyncAPI subjects | 01 |
| 05 | Gateway | Kong AI Gateway; uninstall kgateway | 01,03 |
| 06 | kagent base | kagent control plane (Python ADK); placeholder CRDs | 01,03,04,05 |
| 07 | Agent runtime | port reference → orchestrator+worker; **mem0 removed**; `shared/py-common/` | 06 |
| 08 | Memory | memory-svc/session-svc/rerank-svc; `POST /retrieve` prod-ready | 02,07 |
| 09 | Tools+sandbox | CubeSandbox cluster + RuntimeClass + mcp-registry/runner + 3 tools | 07 |
| 10 | A2A interop | a2a-adapter; Agent Cards; JSON-RPC 2.0 | 06,07 |
| 11 | Governance | OPA constraints + ClickHouse audit + OTTL enforce | 03,07 |
| 12 | Evaluation | eval-svc 5 judges + 4-tool harness + golden datasets | 03,07 |
| 13 | CI/CD GitOps | per-service CI + Image Updater + Argo Rollouts canary + Trivy | all |
| 14 | AWS parity | replicate on K3s-on-EC2 (identical manifests) | 13 |

**First usable stack** = after **Stage 07** (critical path `01 → 03+04+05 → 06 → 07`): `POST /chat/stream`
returns a streamed orchestrator→worker response, with a Langfuse trace tree + a Postgres checkpoint.
Stage 08 (memory/RAG) is the first enrichment after that.

## 6. Immediate next actions (Stage 01 — start now)

1. `platform/cluster/k3d-local/` — k3d cluster definition + Make target.
2. `platform/argocd/root.yaml` — App-of-Apps root → `platform/argocd/applications/`.
3. `platform/argocd/projects/platform.yaml` — AppProject scoping.
4. Wire `make local-up` / `make local-down`.
Gate: `make local-up` → running k3d + healthy ArgoCD; `kubectl get applications -n argocd` root synced;
identical on macOS + Linux. Folder discipline (README + FLOW.mmd) on every new dir.

## 7. What we are NOT building

No EKS/kind/kubeadm (K3s only) · no service mesh · no Kafka/Pulsar/Redis-Streams/Rabbit · no
Temporal/Airflow · no Go ADK · no kgateway · no Mem0/Neo4j/Kuzu · no pgvector/Weaviate/Pinecone · no
vanilla OTel-Collector/kube-prometheus-stack/Promtail · no Kyverno · no Flux/Jenkins/Tekton · no
distributed locks · no `/v1/` internal prefixes · no prompt/completion bodies in span attributes · no
second stack per concern (duplicate-stack anti-pattern).
