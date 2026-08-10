# Architecture Decision Records

This directory contains the immutable decision records for the platform. ADRs are append-only: a new ADR supersedes an old one; old ones are never edited. The Michael Nygard format is followed: Status, Date, Context, Decision, Consequences, Alternatives considered, References.

## Index

| ID | Title | Status | Layer |
|---|---|---|---|
| [0001](0001-monorepo-layout.md) | Monorepo layout for platform and reference workload | Accepted | platform-wide |
| [0002](0002-seven-layer-mapping.md) | Seven-layer mapping as the platform navigation taxonomy | Accepted | platform-wide |
| [0003](0003-protocols-mcp-and-a2a.md) | Adopt MCP and A2A as the platform's two protocol standards | Accepted | L3, L5 |
| [0004](0004-graph-memory-graphiti-falkordb.md) | Graphiti on FalkorDB as the temporal knowledge graph memory engine | Accepted | L4 |
| [0005](0005-tool-sandbox-cubesandbox.md) | CubeSandbox as the tool execution sandbox | Accepted | L5 |
| [0006](0006-observability-alloy-lgtmp-langfuse.md) | Grafana Alloy as the unified telemetry collector; LGTM-P + Langfuse as backends | Accepted | L7 |
| [0007](0007-message-bus-nats-jetstream.md) | NATS JetStream as the east-west message bus | Accepted | L2 |
| [0008](0008-cicd-github-actions-argocd.md) | GitHub Actions for CI, ArgoCD for CD | Accepted | platform-wide |
| [0009](0009-runtime-class-cube.md) | Register RuntimeClass "cube" for sandboxed pod execution | Accepted | L5 |
| [0010](0010-cluster-substrate-k3s.md) | K3s as the cluster substrate, locally and on AWS | Accepted | platform-wide |
| [0011](0011-base-platform-kagent.md) | Adopt kagent as the base agentic platform; configure for HA | Accepted | L2, L3, L5 |
| [0012](0012-gateway-kong-over-kgateway.md) | Replace kgateway with Kong AI Gateway at the request perimeter | Accepted | L1 |

## Cross-cutting doctrines (referenced by multiple ADRs)

ADRs lock in *infrastructure decisions*. Cross-cutting *engineering doctrines* (context engineering, heuristic engineering, RAG architecture, harness engineering, testing strategy) live under `docs/protocols/` and are referenced by these ADRs as needed. The doctrines are not ADRs themselves because they describe *how the platform thinks*, not *what the platform deploys*. Both are required reading.

| Doctrine document | What it codifies |
|---|---|
| [context-engineering](../protocols/context-engineering.md) | Selection / Retrieval / Compression / Persistence of agent context |
| [heuristic-engineering](../protocols/heuristic-engineering.md) | Codified decision rules in orchestrator and worker |
| [rag-architecture](../protocols/rag-architecture.md) | Hybrid search + RRF + reranking + RAGAS gates |
| [harness-engineering](../protocols/harness-engineering.md) | The four-tool evaluation harness composition |
| [testing-strategy](../protocols/testing-strategy.md) | Per-service unit / integration / contract / load / chaos coverage |

## When a new ADR is required

If a decision changes a contract, is expensive to reverse, or will be questioned later, write an ADR. If the decision is "we'd just refactor it next week," skip it.

## Workflow

1. Confirm the decision is irreversible enough to warrant an ADR.
2. Read the most recent five ADRs to match tone and detail.
3. Draft Context first. If you cannot write it without listing more than five forces, the decision is likely two decisions; split it.
4. Draft Decision in one or two sentences, imperative voice.
5. List at least two Alternatives. Steelman each before rejecting.
6. List Consequences. The negatives section must be non-empty.
7. Open a PR with Status "Proposed."
8. On merge, change Status to "Accepted" and set the date.
9. Update this index.

## Supersession

To replace an accepted ADR, write a new ADR that:

- References the old ADR by number in Context.
- Sets the old ADR's Status to "Superseded by NNNN."
- Explains what changed and why.

Never edit the body of an accepted ADR.
