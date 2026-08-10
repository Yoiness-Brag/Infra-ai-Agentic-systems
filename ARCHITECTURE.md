# Platform Architecture

This document is the whole-system reference. It describes how the seven layers of the agentic-system model are realized as concrete infrastructure components and how requests, events, and telemetry flow across them.

For terse layer-specific contracts, see `docs/layers/L1..L7-*/README.md`. For decision rationale, see `docs/adr/`. For platform-wide doctrine, see `docs/protocols/`.

## Design intent

The platform exists to provide every property an agentic workload requires from the substrate it runs on, so that the workload itself does not have to re-implement those properties. Concretely:

1. A north-south entry plane that authenticates, enforces per-app quotas, sanitizes input, and routes to the correct workload.
2. An east-west bus for inter-service communication with at-least-once delivery.
3. A reasoning runtime that runs agents as Kubernetes resources with isolated context windows, controlled tool use, and bounded execution.
4. A unified memory plane exposing one API over short-term, semantic (with hybrid RAG), and temporal-graph memory.
5. A tool plane with kernel-level sandboxing for any code an agent generates.
6. A governance plane enforcing policy at admission, perimeter, and telemetry egress.
7. An observability plane capturing OTel GenAI-aware traces, metrics, logs, and continuous profiles, plus the evaluation harness that closes the loop on workload behavior.

The platform is opinionated. We make choices and record them as ADRs. We do not provide every alternative; we provide the alternative we believe is correct and document why.

## Base platform: kagent

The platform extends the CNCF Sandbox project **kagent** (accepted May 22, 2025). kagent provides the Kubernetes-native agentic substrate: Agent CRDs, ToolServer CRDs, prompt templates, A2A delegation, context compaction, OTel tracing, RBAC, HITL, multi-runtime (Python ADK ~15s startup; Go ADK ~2s startup).

The kagent controller deploys with `replicaCount: 3` and leader election. Engine pods are stateless and horizontally scalable. State lives in Postgres (LangGraph checkpoints), Graphiti-on-FalkorDB (long-term), NATS JetStream (in-flight subtasks), Redis (short-term). This makes kagent a distributed system in the operational sense: HA, no single point of failure given proper deployment, horizontally scalable workers. See ADR-0011.

We deliberately do not re-implement what kagent already gives us. We extend it where its defaults do not match the requirements documented in our ADRs:

| Property kagent provides | Property we add |
|---|---|
| Generic K8s ingress via kgateway | Kong AI Gateway with `ai-proxy-advanced`, `ai-semantic-cache`, `ai-rate-limiting-advanced`, AI guardrails (ADR-0012) |
| Generic K8s pod sandboxing | CubeSandbox cluster registered as `RuntimeClass cube`, sub-60 ms cold start (ADR-0005, ADR-0009) |
| Built-in vector-backed memory | `memory-svc` over Graphiti-on-FalkorDB + Qdrant hybrid search + Redis (ADR-0004) |
| Pluggable evaluation | Four-tool harness composition: DeepEval + Promptfoo + Ragas + Inspect AI, plus the five online LLM-as-judge metrics (`docs/protocols/harness-engineering.md`) |
| LLM provider routing left to the framework | Kong `ai-proxy-advanced` performs cross-provider failover, semantic routing, circuit breaking on OpenAI, Anthropic, Gemini, GLM, Kimi 2, Ollama |

Runtime selection: Python ADK is the default for the reference workload (first-class LangGraph integration). Go ADK is available per-agent via the `runtime` field for workloads that need sub-3-second pod startup.

## The platform doctrines (cross-cutting)

Five doctrines apply across every layer:

| Doctrine | Document | Owns |
|---|---|---|
| **Context engineering** | `docs/protocols/context-engineering.md` | Selection / Retrieval / Compression / Persistence of what enters the model's context window |
| **Heuristic engineering** | `docs/protocols/heuristic-engineering.md` | Codified decision rules in the orchestrator and worker (dispatch, model selection, compaction triggers, termination budgets) |
| **RAG architecture** | `docs/protocols/rag-architecture.md` | Hybrid search (dense + sparse, RRF fusion) + reranking + RAGAS gates |
| **Harness engineering** | `docs/protocols/harness-engineering.md` | The four-tool eval composition: DeepEval + Promptfoo + Ragas + Inspect AI |
| **Testing strategy** | `docs/protocols/testing-strategy.md` | Per-service unit / integration / contract / load / chaos / E2E coverage |

## Seven-layer mapping (concrete)

### Layer 1 — Interface and Entry

Inbound HTTPS and SSE terminates at **Kong AI Gateway**. Plugins: `jwt` (per-app), `ai-rate-limiting-advanced` (10 rps + token budgets), `ai-semantic-cache` (Redis-backed), `ai-prompt-guard`, `request-transformer`, `ai-proxy-advanced` for cross-provider LLM routing, `prometheus`, `opentelemetry`. cert-manager issues TLS. See ADR-0012.

Kong is also the egress point for outbound LLM calls; `ai-proxy-advanced` selects providers with failover and circuit breaking.

### Layer 2 — Orchestration and Control Plane

kagent reconciles agent execution. **NATS JetStream** (3-replica, R3 streams) carries subtasks on `agents.subtask.<session_id>` and results on `agents.result.<session_id>`. The Postgres-backed LangGraph checkpointer persists workflow state. KEDA scales `agent-worker` on consumer lag. See ADR-0007.

The Anthropic orchestrator-worker pattern is realized as `agent-orchestrator` (lead, larger model, persists plan to memory) publishing subtasks, `agent-worker` consuming.

### Layer 3 — Agent Runtime

Each agentic workload is a kagent `Agent` CRD that references: `systemPrompt`, `model`, `toolServers`, `memory`, `a2aSkills`, `hitl`, `contextBudget`, `maxSteps`, `runDeadline`, `tokenBudget`, `costBudgetUsd`. The platform provides `agent-orchestrator`, `agent-worker`, `a2a-adapter`. Each workload runs in its own namespace with default-deny NetworkPolicies. Heuristics from `docs/protocols/heuristic-engineering.md` guard the run.

### Layer 4 — Context and Memory

`memory-svc` is the single API over four backends:

- **Graphiti on FalkorDB** — temporal knowledge graph (bi-temporal).
- **Qdrant** — vector store with native hybrid search.
- **Redis** — short-term + idempotency dedup.
- **Postgres** — LangGraph checkpoints + RLS-scoped app data.

`POST /retrieve` is the platform's RAG endpoint: hybrid search (dense + sparse) → RRF fusion → `rerank-svc` (default `bge-reranker-v2-m3`) → top-K reranked chunks. RAGAS gates: Faithfulness > 0.90, Answer Relevancy > 0.85, Context Precision > 0.80, Context Recall > 0.75. See `docs/protocols/rag-architecture.md`.

`session-svc` compacts long conversations (summarization, sliding-window, selective promotion).

### Layer 5 — Tooling and Integration

`mcp-registry` is the tool catalog. `mcp-sandbox-runner` invokes tools inside CubeSandbox via the E2B SDK. CubeSandbox provides sub-60 ms cold start, KVM-grade isolation, eBPF-enforced egress (CubeVS). `RuntimeClass cube` is registered for full-pod sandboxing as an alternative integration model.

Three reference tools: `web-search`, `doc-search` (over Qdrant via memory-svc), `code-exec`.

`a2a-adapter` exposes every workload's Agent Card at `/.well-known/agent.json` and accepts JSON-RPC 2.0 task delegations.

### Layer 6 — Safety, Policy and Governance

Defense in depth at four enforcement points:

1. **Admission**: OPA Gatekeeper.
2. **Request perimeter**: Kong AI guardrails.
3. **Telemetry egress**: Alloy OTTL processors redact PII before export.
4. **Audit trail**: ClickHouse `platform_audit` table, 90-day default retention.

RBAC at three levels: Kong consumer/key, K8s RBAC, kagent Agent CRD.

### Layer 7 — Observability, Reliability and Optimization

**Grafana Alloy** is the unified collector. ADR-0006. One agent replaces vanilla OTel Collector, kube-prometheus-stack, Promtail, and a separate profiling agent. Alloy fans out to **Mimir** (metrics + alerting via Mimir Ruler), **Loki** (logs), **Tempo** (traces), **Pyroscope** (continuous profiling), and **Langfuse v3** (GenAI prompt traces + eval scores).

`eval-svc` runs the five LLM-as-judge metric prompts ported from the reference workload (online) and drives the four-tool harness composition (DeepEval + Promptfoo + Ragas + Inspect AI) in CI. See `docs/protocols/harness-engineering.md`.

## End-to-end request flow

The whole-system flow is in `docs/overview/00-platform-overview.mmd`. In words:

1. External caller sends HTTPS to a Kong route at `https://gw.platform.local/chat/stream` with a Bearer JWT.
2. Kong validates JWT, applies per-app token budget, consults semantic cache, sanitizes prompt, routes to the workload's `agent-orchestrator` Service.
3. `agent-orchestrator` opens a LangGraph run with a Postgres checkpoint, applies context-engineering doctrine to assemble the initial context (system prompt + retrieved chunks via `memory-svc /retrieve` + session memory), persists the plan to Graphiti, publishes subtasks on `agents.subtask.<sid>`.
4. `agent-worker` pods (KEDA-autoscaled on JetStream lag) consume subtasks, call `memory-svc /retrieve` for grounding (hybrid search + rerank), call LLMs through Kong `ai-proxy-advanced`, invoke tools via `mcp-sandbox-runner` → CubeSandbox, apply heuristics (model selection, loop detection, deadline enforcement), publish results.
5. `agent-orchestrator` reconciles results, updates Graphiti episodes (bi-temporal invalidation when facts change), streams response back through Kong.
6. Every step emits OTLP. Alloy fans out to Mimir / Loki / Tempo / Pyroscope / Langfuse with PII redaction and tail sampling.
7. `eval-svc` scores Langfuse traces continuously and uploads scores back; DeepEval / Ragas / Inspect AI suites run in CI on every change to L3, L4, L5, L7 services.

## What this platform deliberately does not do

- No service mesh (no Istio, no Linkerd). Kong handles north-south; NATS handles east-west.
- No Kafka. NATS JetStream until proven insufficient.
- No vanilla OTel Collector, no kube-prometheus-stack, no Promtail, no standalone profiling agent. Grafana Alloy replaces all four.
- No Temporal or Airflow. LangGraph plus orchestrator-worker is sufficient.
- No Neo4j. FalkorDB is the graph engine.
- No `/v1/` URL prefixes on internal platform APIs. Internal contract evolves via schema (Pydantic + OpenAPI + AsyncAPI) under `shared/proto/`.

## References

Every claim is backed by a validated source. See `docs/overview/03-references.md` for the index, `docs/adr/` for the locked-in decisions, and `docs/protocols/` for the cross-cutting doctrines.
