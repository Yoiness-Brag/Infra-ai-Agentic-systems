# Design Principles

This document captures the principles that govern every architectural choice in this platform. When a future ADR is being written and the answer is not obvious, the answer is the principle that applies.

## 1. The platform is the product, not the agent

The agentic workload that ships in `services/L3-agent-runtime/` is a reference workload. It exists to validate the platform end to end. The real product is the platform underneath. Every design choice is evaluated against the question: "does this make life easier for the next agentic workload that lands here?"

## 2. Extend, do not re-implement

We build on the CNCF Sandbox project kagent. We do not rewrite agent-as-CRD scheduling, prompt-template ConfigMaps, ToolServer CRDs, context compaction, A2A delegation, or human-in-the-loop gates. Where kagent's default is a poor fit for a stated requirement, we extend or replace that specific component with an ADR-locked alternative (Kong instead of kgateway, CubeSandbox instead of generic sandboxing, Graphiti-on-FalkorDB instead of pluggable BYO memory).

## 3. One ADR per irreversible decision

Decisions that change a contract, are expensive to reverse, or will be questioned later are recorded as ADRs in `docs/adr/`. ADRs are immutable; we supersede them by writing a new one. If a decision is "we would refactor it next week," it is not an ADR.

## 4. Seven layers, no leakage

Every infrastructure component, service, and decision maps to exactly one of the seven layers. When a feature naturally spans two layers, it goes in the higher-numbered one and exposes a contract to the lower-numbered one. For example, governance (L6) cuts across L1 through L5, but each enforcement point lives in the layer it enforces against, with the L6 README documenting the inventory.

## 5. Folder discipline is non-negotiable

Every folder has a `README.md`, a `FLOW.mmd`, and where applicable a `runbook.md`. A reader who lands in any folder can orient themselves without leaving it. CI checks the discipline.

## 6. Distributed-system properties are explicit

The platform commits to specific distributed-system properties, codified in `ARCHITECTURE.md`:

- At-least-once delivery on NATS JetStream subjects, with idempotency keys on every async edge and dedup tables in Redis with a TTL longer than the broker redelivery window.
- Circuit breaker on every external dependency (LLM provider, FalkorDB, Qdrant, MCP tool call).
- Connection pooling on Postgres, Redis, NATS, and the LLM gateway.
- Bounded concurrency via NATS consumer ack budgets, plus KEDA scaling on consumer lag rather than CPU.
- Liveness, readiness, and startup probes per service. Readiness flips false on dependency outage so Kong stops routing to the unhealthy pod.
- Graceful shutdown: SIGTERM drains in-flight requests, acks pending NATS messages, closes pools.
- Schema-first contracts: OpenAPI for HTTP, AsyncAPI for NATS subjects, A2A Agent Card for inter-agent, MCP manifest for tools. All schemas live in `shared/proto/`.

## 7. Defense in depth for policy

Governance is enforced at four points, not one:

1. Admission (OPA Gatekeeper rejects non-compliant K8s resources).
2. Request perimeter (Kong AI guardrails sanitize input, detect prompt injection).
3. Telemetry egress (OTel Collector OTTL processors redact PII before export).
4. Audit storage (ClickHouse retains the full record for 90 days by default).

## 8. Observability is OpenTelemetry-native

All instrumentation uses the OpenTelemetry GenAI semantic conventions (`gen_ai.*`). Vendor-specific SDKs (Langfuse callbacks, Prometheus exporters) coexist with OTel but do not replace it. The OTel Collector is the central pipeline; everything downstream is a backend.

## 9. Anti-patterns we deliberately reject

The following were considered and rejected. Each rejection has rationale in the corresponding ADR:

- **Service mesh (Istio, Linkerd)**: adds operational cost without justified benefit at our scale; Kong covers north-south, NATS covers east-west, cert-manager covers mTLS.
- **Kafka**: NATS JetStream is sufficient at our event volume; Kafka's operational overhead is not justified until we have data-pipeline use cases.
- **Temporal, Airflow**: LangGraph plus the orchestrator-worker pattern with Postgres checkpoints covers the workflow needs. Adding a dedicated workflow engine is a separate decision for a separate time.
- **Distributed locks**: Postgres advisory locks suffice where strictly needed. Designs that need cluster-wide locks are usually missable redesigns.
- **Neo4j**: GPL license creates commercial friction; FalkorDB (BSD-3, Cypher-compatible, Redis-based) is the cleaner default.
- **Storing full prompts in span attributes**: PII risk plus size limits. Prompts go in span events under `gen_ai.content.prompt` so the OTel Collector can drop or redact them via OTTL processors before they leave the cluster.

## 10. Terminology discipline

The following terms are not used:

- "Tenancy" — use "per-app isolation," "workload separation," or "namespace boundary."
- "Bootstrap" — use "cluster provisioning," "platform initialization," or "stand-up."

Naming is part of the contract. Sloppy terms produce sloppy designs.

## 11. Local-first, cloud-equivalent

Every manifest in `platform/` works the same way on a local k3d cluster as it does on K3s-on-EC2. Differences are isolated to `platform/cluster/{k3d-local,k3s-on-vm}/` overlays. No `if local then X else Y` logic in service code.

## 12. Composition over framework lock-in

The platform integrates several open source projects (kagent, Kong, Langfuse, Graphiti, CubeSandbox, K3s, ArgoCD, Grafana Alloy). Each remains the upstream's responsibility for its own maintenance; we configure and integrate, we do not fork. If we ever do fork, that is an ADR.

## 13. Five doctrines guide every design choice

When an architectural question is not answered by an ADR, the answer is the doctrine that applies:

- **Context engineering** (`docs/protocols/context-engineering.md`) — anything about what enters the model's context window.
- **Heuristic engineering** (`docs/protocols/heuristic-engineering.md`) — anything about agent decision logic that should be deterministic and observable rather than implicit in the LLM.
- **RAG architecture** (`docs/protocols/rag-architecture.md`) — anything about retrieval, ranking, or chunking.
- **Harness engineering** (`docs/protocols/harness-engineering.md`) — anything about evaluating whether the agent produces correct output.
- **Testing strategy** (`docs/protocols/testing-strategy.md`) — anything about verifying that a service component behaves correctly under normal and adverse conditions.

A design choice that contradicts a doctrine requires either a written exception in the relevant `services/<svc>/README.md` or a revised doctrine document. Doctrines are not immutable like ADRs; they evolve, but their evolution is also reviewed in a PR.
