# ADR-0002: Seven-layer mapping as the platform navigation taxonomy

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

The platform integrates many open-source components: kagent, Kong, NATS JetStream, KEDA, FalkorDB, Qdrant, Postgres, Redis, ClickHouse, MinIO, OPA Gatekeeper, cert-manager, OTel Collector, Mimir, Loki, Tempo, Grafana, Langfuse, CubeSandbox, MCP, A2A. Without a navigation taxonomy, a new joiner cannot place a component, a documentation reader cannot find the responsible folder, and an ADR cannot situate itself in the architecture.

The reference workload in the Fareed Khan repository, and the broader industry consensus (JIN, Asimsultan, Educative.io), converge on a seven-layer model: Interface and Entry, Orchestration and Control Plane, Agent Runtime, Context and Memory, Tooling and Integration, Safety/Policy/Governance, Observability/Reliability/Optimization.

We considered three alternative taxonomies:

1. The seven-layer model from the Fareed Khan article.
2. A traditional three-tier (data plane, control plane, application) split.
3. A Kubernetes-native split by resource type (CRDs, Deployments, Services, etc.).

The three-tier split conflates governance, observability, and tooling under "control plane" and provides no answer for where MCP belongs. The K8s-native split organizes by implementation detail rather than responsibility, which is bad navigation. The seven-layer model is the only one that maps cleanly to the responsibilities a workload expects from the platform.

## Decision

We adopt the seven-layer model as the navigation taxonomy for the entire repository. Every infrastructure component, service, and ADR maps to exactly one of the seven layers. Folder names under `platform/`, `services/`, and `docs/layers/` carry the layer number as a prefix (`L1-`, `L2-`, ..., `L7-`).

When a feature spans two layers, it lives in the higher-numbered layer and exposes a contract documented in the lower layer's `components.md`.

## Consequences

Positive:

- New joiners orient in minutes via `docs/overview/00-platform-overview.md`.
- ADRs are discoverable by layer number in their title.
- Code review can ask "which layer is this changing?" and require an answer.
- Cross-references between docs are stable: `docs/layers/L4-context-and-memory/README.md` will always exist at that path.

Negative:

- Some components (notably governance and observability) cut across all layers. The mapping puts them in their own layers (L6 and L7), but readers must still understand the cross-cutting nature.
- A future feature that does not fit any layer would require either superseding this ADR or stretching one layer's definition.

Neutral:

- The taxonomy is industry-aligned, so a new joiner who has read the Medium articles has a head start.

## Alternatives considered

- **Three-tier split (data plane, control plane, app)**: rejected because it does not give a home to MCP tooling and conflates governance with control.
- **K8s resource-type split**: rejected because it organizes by implementation rather than responsibility.

## References

- Fareed Khan, "Building the 7 Layers of a Production-Grade Agentic AI System": https://levelup.gitconnected.com/building-the-7-layers-of-a-production-grade-agentic-ai-system-37ee5d941f1c
- JIN deep dive: https://medium.com/aimonks/the-7-layers-of-a-production-grade-agentic-ai-system-an-architects-deep-dive-b00e78459fe6
- Reference repository: https://github.com/FareedKhan-dev/production-grade-agentic-system
