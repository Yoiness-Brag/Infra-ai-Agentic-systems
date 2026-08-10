# Glossary

Terminology used consistently across the repository. Where a term has industry-standard meaning, the standard meaning applies; where multiple meanings are common, this glossary picks one and that is the one used here.

## A

**A2A (Agent-to-Agent)** — Open standard, hosted by the Linux Foundation since June 2025, for inter-agent communication. Defines Agent Cards, Tasks, and a JSON-RPC 2.0 transport over HTTP and SSE.

**ACP (Agent Communication Protocol)** — IBM's REST-based agent protocol. Officially merged under A2A at the Linux Foundation. We treat ACP-compatible agents as A2A agents.

**Admission** — In Kubernetes, the validation phase that runs before a resource is persisted to etcd. We use OPA Gatekeeper at admission to reject non-compliant resources before they take effect.

**Agent Card** — The A2A discovery artifact published at `/.well-known/agent.json`. Lists what an agent can do, what skills it exposes, and how to reach it.

**Agentic RAG** — RAG variant in which the agent itself decomposes a query into sub-queries, runs them in parallel through the retrieval stack, and reconciles the results. The orchestrator-worker pattern applied to retrieval. See `docs/protocols/rag-architecture.md`.

**AGNTCY** — Cisco's agentic interop initiative, also merged under the Linux Foundation umbrella. Subsumed by A2A for our purposes.

**ai-proxy-advanced** — Kong AI Gateway plugin that performs multi-LLM-provider routing, semantic load balancing, failover, and circuit breaking.

**ai-semantic-cache** — Kong AI Gateway plugin that caches LLM responses by embedding similarity, backed by a vector store (we use Redis with redis-vss).

**Alloy (Grafana Alloy)** — Grafana Labs' OpenTelemetry Collector distribution with built-in Prometheus, Loki, and Pyroscope pipelines. The platform's unified telemetry collector per ADR-0006. Replaces vanilla OTel Collector + kube-prometheus-stack + Promtail + standalone profiling agent. 100% OTLP-compatible; native clustering; web UI at port 12345.

**App-of-Apps** — ArgoCD pattern in which one root `Application` references a directory of child `Application` resources, allowing the whole platform to be reconciled from a single Git commit.

## B

**bge-large-en-v1.5** — The platform's default self-hosted embedding model. 1024-dim. From the BAAI BGE family.

**bge-reranker-v2-m3** — The platform's default cross-encoder reranker, used by `rerank-svc` to re-rank a top-50 hybrid-search result to a top-K. From the BAAI BGE family. Self-hosted.

**BM25** — Sparse keyword-retrieval scoring function. One half of the hybrid-search pair (the other half is dense embedding similarity). Implemented in Qdrant via sparse vectors.

## C

**Circuit breaker** — Fault-tolerance pattern that fails fast after a threshold of failures, preventing cascading collapse. We wrap every LLM provider call, FalkorDB call, Qdrant call, and MCP tool call.

**ClickHouse** — Columnar OLAP database. Used as the Langfuse v3 trace backend and as the audit-trail store.

**Compaction (conversation)** — The process of summarizing older turns of a conversation into a single episode so the recent turns can stay in the context window. Owned by `session-svc` at the L4 layer; triggered by the `compaction-token-cap` and `compaction-turn-cap` heuristics. See `docs/protocols/context-engineering.md`.

**Context engineering** — The discipline of dynamically assembling the right information into an agent's context window. Six layers (system instructions, semantic context, operational memory, conversational history, retrieval results, tool access); four dimensions (Selection, Retrieval, Compression, Persistence). The platform's cross-cutting doctrine at `docs/protocols/context-engineering.md`.

**Cube, CubeMaster, Cubelet, CubeProxy, CubeShim, CubeVS** — The five components of CubeSandbox. CubeMaster orchestrates; Cubelet manages sandbox lifecycle per node; CubeProxy routes via `<port>-<sandbox_id>.<domain>`; CubeShim implements containerd Shim v2; CubeVS is the eBPF virtual switch for inter-sandbox network isolation.

**CubeSandbox** — Tencent Cloud's open-source agent sandbox (Apache 2.0, RustVMM + KVM). Sub-60 ms cold start, <5 MB per sandbox, E2B SDK drop-in compatible.

## D

**DeepEval** — Pytest-style LLM evaluation framework from Confident AI. Owns application-unit eval in the platform's harness composition. See `docs/protocols/harness-engineering.md`.

## E

**E2B SDK** — De facto standard SDK interface for AI agent code execution sandboxes. We use it as the client interface; CubeSandbox is the server implementation.

**Episode** — A unit of memory in Graphiti: a single event or assertion, with bi-temporal validity.

## F

**FalkorDB** — BSD-3 graph database, Cypher-compatible, Redis-based. Used as the Graphiti backend.

**Foundation stage (STAGE-00)** — The first stage of platform construction. Produces only documentation; no service code.

## G

**Graphiti** — Apache 2.0 temporal knowledge graph library by Zep, with bi-temporal modeling (valid time vs ingestion time). Used as the core of our memory plane.

**GraphRAG** — RAG variant that uses a knowledge graph for retrieval, suited to global queries about relationships across an entire corpus. The platform provides a partial GraphRAG via Graphiti (the `graph-for-relations` heuristic); we do not implement Microsoft GraphRAG-style community-summary precomputation.

**Guardrails (Kong AI)** — Kong plugins that perform PII sanitization and prompt-injection detection at the request perimeter.

## H

**Harness engineering** — The discipline of building evaluation infrastructure around an agent runtime. The platform adopts a four-tool composition: DeepEval + Promptfoo + Ragas + Inspect AI. See `docs/protocols/harness-engineering.md`.

**Heuristic engineering** — The discipline of codifying agent decision rules (when to dispatch, when to compact, when to escalate, when to abort) as deterministic, observable checks rather than implicit LLM reasoning. See `docs/protocols/heuristic-engineering.md`.

**HITL (Human-in-the-Loop)** — Pattern where a tool call (or any policy-flagged action) pauses execution and waits for human approval. kagent provides the primitive; we wire it through audit events on `audit.hitl.<workload>`.

**Hybrid search** — Retrieval that combines dense (embedding) and sparse (BM25) results into a single ranked list via Reciprocal Rank Fusion. The platform default. Implemented in Qdrant via `FusionQuery(fusion=Fusion.RRF)`. See `docs/protocols/rag-architecture.md`.

## I

**Inspect AI** — UK AI Security Institute's composable evaluation framework. Owns safety/capability evals in the platform's harness composition.

## J

**JetStream** — NATS's persistence layer providing durable streams, consumer groups, and replay. The platform message bus.

## K

**kagent** — CNCF Sandbox project (joined May 22, 2025) by Solo.io. The Kubernetes-native agentic AI framework we use as our base. Provides Agent CRDs, ToolServer CRDs, A2A delegation, context compaction. Two runtimes: Python ADK (~15s startup, LangGraph-native) and Go ADK (~2s startup). Deployed for HA with 3-replica controller + leader election per ADR-0011.

**KEDA** — Kubernetes Event-driven Autoscaling. We use it to scale `agent-worker` on NATS JetStream consumer lag.

**kgateway** — The Envoy-based gateway (formerly Gloo) that ships with kagent by default. We replace it with Kong AI Gateway for the LLM-specific plugin set.

**K3s** — CNCF-certified Kubernetes distribution, single binary. The platform's only cluster substrate: locally via k3d, in staging via K3s-on-VM, in AWS production via K3s-on-EC2. No EKS option (see ADR-0010 — one-stack-per-use-case).

## L

**Langfuse** — Open-source LLM observability platform. v3 splits into Web and Worker tiers, with Postgres + ClickHouse + Redis + S3 as backing stores. We self-host.

**LangGraph** — State-machine framework for LLM workflows. Used as the workflow engine inside `agent-orchestrator` and `agent-worker`, with `langgraph-checkpoint-postgres` for state persistence.

**LGTM-P** — Grafana's observability bundle as we deploy it: Loki (logs), Grafana (visualization), Tempo (traces), Mimir (metrics), Pyroscope (profiles). The trailing P (Pyroscope) is new in this revision; ADR-0006 brings continuous profiling into scope from day one.

**LLM-as-judge** — Pattern where one LLM scores the output of another against rubric prompts. We use the five-metric pipeline (hallucination, helpfulness, relevancy, conciseness, toxicity) ported from the reference workload, run online by `eval-svc`.

## M

**MCP (Model Context Protocol)** — Linux Foundation open standard (originally Anthropic) for connecting models to tools and data. Each tool is described by a manifest.

**memory-svc** — The platform service that exposes a single API over Graphiti (graph), Qdrant (vector), Redis (short-term), and the LangGraph Postgres checkpointer. Hosts the `/retrieve` endpoint that runs the hybrid-search + reranking pipeline.

**Mimir** — Grafana's distributed Prometheus-compatible metrics store. We also use the Mimir Ruler for alerting (no separate Alertmanager-on-Prometheus).

## N

**Namespace boundary** — Kubernetes namespace used to isolate one workload from another. Reinforced by NetworkPolicies that block cross-namespace traffic except via platform-provided buses, gateways, and shared services. Replaces the term "tenancy."

**NATS JetStream** — The platform message bus. See JetStream.

## O

**OPA Gatekeeper** — Open Policy Agent's Kubernetes admission controller.

**OpenTelemetry GenAI semantic conventions** — Standard set of `gen_ai.*` span attributes for LLM observability (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, etc.). The platform standard.

**Orchestrator-Worker** — Multi-agent pattern from Anthropic Research: a lead agent plans and dispatches, subagents work in parallel in isolated context windows, the lead reconciles. Measured 90.2% uplift over single-agent on Anthropic's research evaluations.

**OTTL** — OpenTelemetry Transformation Language. Used in Alloy's processors (which are the same OTel processors that ship in the vanilla Collector) to redact PII from telemetry before export.

## P

**Per-app isolation** — The platform's workload separation model. Each app is a Kubernetes namespace with its own JWT issuer, its own row-level-security identifier in Postgres, its own NATS subject prefix, and its own NetworkPolicies. Replaces the term "tenancy."

**pgvector** — Postgres extension for vector storage. Used by the LangGraph checkpointer where embeddings sit alongside relational state.

**Platform initialization** — The act of provisioning a fresh cluster and reconciling the platform manifests. Replaces the term "bootstrap."

**Postgres advisory lock** — Lightweight session-scoped lock primitive. Our preference over external distributed locks where strictly needed.

**Promptfoo** — CLI-first YAML-driven LLM evaluation framework, used internally by both Anthropic and OpenAI. Owns prompt-matrix and red-team eval in the platform's harness composition.

**Pyroscope** — Grafana's continuous-profiling backend. CPU and memory flame graphs over time, captured by Alloy from every service. Brought into scope in this revision per ADR-0006.

## Q

**Qdrant** — Vector store with K8s operator. The platform's semantic retrieval engine. Used in hybrid-search mode (dense + sparse with RRF fusion).

## R

**Ragas (RAGAS)** — RAG-specific evaluation framework. Computes Faithfulness, Answer Relevancy, Context Precision, and Context Recall. The platform uses Ragas both online (5% sample of live traces) and in CI (against golden datasets in `evals/datasets/`). Thresholds: Faithfulness > 0.90, Answer Relevancy > 0.85, Context Precision > 0.80, Context Recall > 0.75.

**RAG (Retrieval-Augmented Generation)** — The pattern of fetching external knowledge at query time and adding it to the LLM context. In the platform, RAG is a subset of context engineering. See `docs/protocols/rag-architecture.md`.

**Redis** — Used for: short-term memory, idempotency dedup, Kong rate-limit counters, Kong semantic-cache backing. Single deployment, multiple logical databases.

**Reference workload** — The agentic application ported from the Fareed Khan production-grade-agentic-system repository. Validates the platform end to end.

**rerank-svc** — The platform's cross-encoder reranking service. Default `BAAI/bge-reranker-v2-m3` self-hosted. Reranks the top-50 hybrid-search result to top-K. Logically separate from `memory-svc` (own pod for GPU placement when applicable).

**RRF (Reciprocal Rank Fusion)** — Rank-merging algorithm used by Qdrant to combine dense and sparse retrieval results into one ranked list. Parameter-free (no alpha to tune).

**RuntimeClass** — Kubernetes resource that selects a non-default container runtime. We register `RuntimeClass cube` against CubeShim.

## S

**Saga** — Long-running workflow pattern with compensating actions. `agent-orchestrator` is the saga coordinator for multi-step workloads.

**Semantic chunking** — Chunking content at embedding-distance topic boundaries rather than fixed character counts. The platform default for unstructured text; fixed-size (512/64) fallback for transcripts/logs; AST-aware chunking for source code.

**session-svc** — The platform's conversation-compaction worker. Summarization, sliding-window truncation, selective promotion of episodes from short-term to long-term memory. Lives at L4 (`services/L4-context-and-memory/session-svc/`).

**SLO** — Service-level objective. Each layer README documents its SLOs.

**Span event** — OpenTelemetry construct for attaching structured payloads to a span. We use it for prompt and completion bodies under `gen_ai.content.prompt` and `gen_ai.content.completion` so the collector (Alloy) can drop or redact them before export.

## T

**Tempo** — Grafana's distributed tracing backend.

**ToolServer** — kagent CRD that registers a set of tools an agent can use.

## V

**Validation workload** — Synonym for reference workload.

## W

**Workload separation** — See per-app isolation. Replaces the term "tenancy."
