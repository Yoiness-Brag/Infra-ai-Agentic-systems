# Platform Overview

## What this platform is

A production-grade AI infrastructure platform that hosts agentic workloads on Kubernetes. It is built as a deliberate extension of the CNCF Sandbox project **kagent** (https://kagent.dev), with five additions that close gaps in kagent's defaults:

1. **Kong AI Gateway** at the request perimeter, replacing kagent's default `kgateway`, because Kong 3.8+ ships LLM-specific plugins (`ai-proxy-advanced`, `ai-semantic-cache`, `ai-rate-limiting-advanced`, AI guardrails) that match the Excalidraw design's requirements directly.
2. **CubeSandbox** (Tencent Cloud, Apache 2.0, RustVMM + KVM) as the tool sandbox, registered as a Kubernetes `RuntimeClass` named `cube`, providing sub-60 ms cold start and KVM-grade isolation for any code an agent generates.
3. **Graphiti on FalkorDB** as the temporal knowledge graph memory engine, bi-temporal (valid time + ingestion time), behind a unified `memory-svc` API alongside Qdrant (vector) and Redis (short-term).
4. **Multi-LLM provider routing** via Kong `ai-proxy-advanced` across OpenAI, Anthropic, Gemini, GLM, Kimi 2, and a local Ollama instance, with semantic routing and cross-provider failover.
5. **A Langfuse v3 self-hosted evaluation pipeline** with the five LLM-as-judge metric prompts (hallucination, helpfulness, relevancy, conciseness, toxicity) ported from the reference workload, plus DeepEval offline regression suites.

## What this platform is not

- It is not an agentic application. The reference workload ported from the [Fareed Khan repository](https://github.com/FareedKhan-dev/production-grade-agentic-system) exists only to validate the platform end to end. Real workloads are deployed onto the platform as kagent CRDs.
- It is not a managed service. Operators run the platform themselves on K3s locally and on K3s-on-EC2 on AWS.
- It is not a one-size-fits-all framework. The choices are opinionated and recorded in `docs/adr/`. To deviate, supersede the relevant ADR.

## The seven layers as a navigation key

When you don't know which folder owns something, the layer answers:

| You're looking for | Layer | Where it lives |
|---|---|---|
| API authentication, rate limiting, semantic cache | L1 | `platform/L1-gateway/`, `docs/layers/L1-interface-and-entry/` |
| Agent planning, subtask dispatch, workflow state | L2 | `platform/L2-orchestration/`, `services/L3-agent-runtime/agent-orchestrator/`, `docs/layers/L2-orchestration-control-plane/` |
| Where the agent actually runs | L3 | `services/L3-agent-runtime/`, `docs/layers/L3-agent-runtime/` |
| Memory: graph, vector, short-term, session checkpoints | L4 | `services/L4-context-and-memory/`, `platform/L4-data-plane/`, `docs/layers/L4-context-and-memory/` |
| MCP tools, sandbox, A2A interop | L5 | `services/L5-tooling-integration/`, `tools/`, `docs/layers/L5-tooling-and-integration/` |
| Policy enforcement, audit, RBAC | L6 | `platform/L6-governance/`, `docs/layers/L6-safety-policy-governance/` |
| Metrics, logs, traces, eval pipeline | L7 | `platform/L7-observability/`, `services/L7-evaluation/`, `docs/layers/L7-observability-reliability/` |

## Two pillars to monitor continuously

Per the seven-layer model the platform supports both pillars equally:

1. **Workload behavior** — reasoning accuracy, tool-usage correctness, memory consistency, policy adherence, context handling across turns and across agents, coordination across multi-agent fan-outs.
2. **System reliability and performance** — latency, availability, throughput, cost efficiency, failure recovery, dependency health of LLMs, vector stores, tools, and APIs.

The L7 observability plane plus the `eval-svc` close both pillars. Metrics, traces, and continuous profiles cover pillar 2 via Grafana Alloy → LGTM-P. The five LLM-as-judge prompts plus the four-tool harness composition cover pillar 1.

## Five cross-cutting doctrines

Beyond the seven layers, the platform commits to five engineering disciplines that cut across every layer. Each has its own doctrine document under `docs/protocols/`:

| Doctrine | Document | What it codifies |
|---|---|---|
| **Context engineering** | [context-engineering.md](../protocols/context-engineering.md) | The four dimensions (Selection / Retrieval / Compression / Persistence) and the six context-window layers that govern what enters the model on every turn |
| **Heuristic engineering** | [heuristic-engineering.md](../protocols/heuristic-engineering.md) | The codified, observable decision rules in `agent-orchestrator` and `agent-worker` — dispatch, model selection, compaction triggers, termination budgets |
| **RAG architecture** | [rag-architecture.md](../protocols/rag-architecture.md) | Hybrid dense+sparse search with Reciprocal Rank Fusion, cross-encoder reranking, semantic chunking, RAGAS quality gates |
| **Harness engineering** | [harness-engineering.md](../protocols/harness-engineering.md) | The four-tool evaluation composition: DeepEval (app-unit) + Promptfoo (matrices + red-team) + Ragas (RAG-specific) + Inspect AI (safety) |
| **Testing strategy** | [testing-strategy.md](../protocols/testing-strategy.md) | Per-component pyramid: unit → integration (testcontainers) → contract (schemathesis + AsyncAPI) → load (locust) → chaos (toxiproxy) → E2E |

These doctrines are *not* ADRs because they describe how the platform thinks, not what it deploys. Together with the protocol notes (MCP, A2A, OTel GenAI semconv), they are the cross-cutting reading set.

## High-level data flow

See `00-platform-overview.mmd` for the rendered diagram.

A request flows L1 → L2 → L3, fans out east-west on L2 to additional L3 workers, reads and writes L4 memory, calls L5 tools, is governed by L6 at admission and at the perimeter, and emits telemetry to L7 at every step. The eval pipeline reads L7 traces and scores them.

## Reading order for new joiners

1. This document.
2. `ARCHITECTURE.md` at the repository root.
3. The five doctrine documents under `docs/protocols/`: context-engineering, heuristic-engineering, rag-architecture, harness-engineering, testing-strategy. They are short; read all five.
4. The README of the layer you'll work on.
5. The ADRs that touch the layer you'll work on (search ADR titles for the layer number).
6. The stage where your work fits in `docs/stages/`.
