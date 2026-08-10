# ADR-0011: Adopt kagent as the base agentic platform with the Python ADK runtime; configure for HA

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

Building the seven layers of a production-grade agentic platform from scratch is months of work and produces something with no community, no upstream maintenance, no ecosystem integration. We surveyed existing open-source projects that already cover the same scope and chose **kagent**:

- CNCF Sandbox project (accepted May 22, 2025), Apache 2.0.
- Built by Solo.io (the founders of Istio).
- 3,164+ contributors across 975+ organizations by April 2026.
- Stated purpose: the Kubernetes-native agentic AI framework.

### kagent architecture

kagent has four components, all deployed as standard Kubernetes workloads:

1. **Controller** (Go). Standard controller-runtime pattern. Reconciles `Agent`, `ModelConfig`, `ToolServer` CRDs. Supports multi-replica with leader election.
2. **Engine**. Stateless agent runtime. Ships two implementations: Python ADK (built on Google ADK, supports LangGraph, CrewAI, Google ADK, OpenAI Agents SDK) with ~15 s pod startup, and Go ADK (native Go) with ~2 s startup but narrower framework coverage. **We pick exactly one** to enforce one-stack-per-use-case.
3. **UI** (Next.js). Operator-facing.
4. **CLI**. Operator-facing.

### Runtime choice: Python ADK exclusively

The reference workload uses LangGraph (`src/agent/workflow.py`, `src/agent/state.py`, `src/agent/nodes.py`). LangGraph is a Python framework with first-class support in the kagent Python ADK runtime. Choosing Go ADK would force a rewrite of the reference workload's reasoning code in Go and would require maintaining two engine deployments in the platform for no architectural benefit.

The ~15 s pod startup overhead is acceptable because:

- `agent-orchestrator` is long-lived (one pod per workload, scaled by request volume; startup happens once at deploy time).
- `agent-worker` is KEDA-autoscaled on consumer lag; the optimization that matters is pod warmth, not startup latency.

If a future workload demonstrably needs sub-3-second cold start for tens of thousands of agent pods, that is a new ADR.

## Decision

We adopt **kagent** as the base platform and use **only the Python ADK runtime**. Go ADK is not deployed.

The kagent agentic substrate (Agent CRDs, ToolServer CRDs, prompt templates, A2A delegation, context compaction, HITL gates, OTel tracing, RBAC, skills-from-Git) is installed via the upstream Helm chart and configured. The five additions documented in other ADRs extend kagent where its defaults do not match the platform's stated requirements:

| Property kagent provides | Platform extension |
|---|---|
| kgateway ingress | Kong AI Gateway (ADR-0012) |
| Generic K8s sandboxing | CubeSandbox + RuntimeClass cube (ADR-0005, ADR-0009) |
| Built-in vector memory | `memory-svc` over Graphiti-on-FalkorDB + Qdrant + Redis (ADR-0004) |
| LLM routing left to framework | Kong `ai-proxy-advanced` with semantic routing and failover |
| No built-in evaluation pipeline | `eval-svc` with 5 LLM-as-judge metrics + 4-tool harness composition |

kagent's built-in vector-backed memory is disabled in our Helm values. We use `memory-svc` exclusively.

### HA configuration

The kagent controller deploys with `replicaCount: 3` and `leaderElection: true`. Engine pods are stateless; state lives in Postgres (LangGraph checkpoints), Graphiti-on-FalkorDB (long-term), NATS JetStream (in-flight subtasks), Redis (short-term). CRDs live in etcd, persisted by Kubernetes.

This is the same HA pattern every production K8s operator follows. kagent meets the operational definition of a distributed system (HA, no single point of failure given proper deployment, horizontally scalable workers).

## Consequences

Positive:

- Months of work avoided. Agent-as-CRD, ToolServer-as-CRD, prompt templates, A2A delegation, context compaction, HITL: all upstream-maintained.
- One engine runtime to operate, one set of pod templates, one upgrade story.
- LangGraph (the reference workload's choice) is first-class on Python ADK.
- CNCF ecosystem alignment.

Negative:

- Cold-start latency of ~15 s on the Python ADK runtime. Mitigated by long-lived orchestrator pods and KEDA-scaled (warm) workers.
- Downstream of kagent's CRD API decisions. A breaking upstream change costs us a migration.
- Replacing kagent defaults (kgateway, generic memory) is integration work that has to track upstream changes.

## Alternatives considered

- **Both Python ADK and Go ADK runtimes (selectable per agent)**: rejected as the duplicate-stack anti-pattern. Two engine runtimes doubles the test surface, doubles the deployment story, doubles the upgrade cadence.
- **Go ADK only**: rejected because the reference workload is LangGraph (Python).
- **Build the platform from scratch** without kagent: rejected because kagent provides ~80% of L3 and a significant chunk of L5 for free.
- **Microsoft Agent Framework**: rejected because not Kubernetes-native; Azure-centric connector set.
- **BeeAI**: rejected as narrower in scope and subsumed under A2A at the Linux Foundation.
- **Build on Google ADK directly**: ADK is an SDK, not a platform. We get it transitively through kagent's Python runtime.

## References

- kagent project site: https://kagent.dev
- kagent GitHub: https://github.com/kagent-dev/kagent
- kagent architecture (Python ADK and Go ADK runtimes documented): https://kagent.dev/docs/kagent/concepts/architecture
- DeepWiki overview of kagent: https://deepwiki.com/kagent-dev/kagent
- CNCF Sandbox project page (accepted May 22, 2025): https://www.cncf.io/projects/kagent/
- Solo.io CNCF contribution: https://www.solo.io/blog/bringing-agentic-ai-to-kubernetes-contributing-kagent-to-cncf
