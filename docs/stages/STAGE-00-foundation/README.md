# Stage 00 — Foundation

## Goal

Produce the documentation contract for the platform. No service code, no Helm values, no cluster provisioning. After Stage 00, a new engineer can read this repository top to bottom and understand the whole platform, the seven layers, every accepted decision, and the implementation roadmap, before any infrastructure exists.

Stage 00 is the answer to: "we are about to spend months building a complex platform; let us first agree what we are building and why."

## Deliverables

By the end of Stage 00, the repository contains:

- `README.md` and `ARCHITECTURE.md` at the root.
- The five `docs/overview/` documents (platform overview, design principles, glossary, references, and the C4 Container diagram).
- All twelve accepted ADRs under `docs/adr/`, plus the ADR index.
- For each of the seven layers under `docs/layers/L1..L7-*/`: a `README.md` and a `FLOW.mmd`. `components.md` and `runbook.md` are stubs to be filled in their respective implementation stages.
- Protocol documents under `docs/protocols/`: MCP, A2A, OTel GenAI semconv.
- The upstream-repo mapping under `docs/reference/`.
- A skeleton README per platform and services folder so that every directory has an orientation document.
- Top-level `Makefile`, `LICENSE`, `.gitignore`.

## Non-goals

- No K3s install. No Helm values populated. No service code. No Dockerfiles. No CI workflows.
- No commitment to a particular cluster provider beyond what is recorded in ADR-0010.
- No production deployment.

## Acceptance criteria

Stage 00 is done when:

1. Every folder in the repository contains either a `README.md` or a `.gitkeep` justifying its absence.
2. Every accepted ADR has Status "Accepted" and a date.
3. Every layer document has a `FLOW.mmd` that renders in Mermaid.
4. The `make docs-check` target passes.
5. A reader who has not seen the project can answer, after a single read-through: "what does the platform do, what are the seven layers, why kagent, why Kong, why CubeSandbox, why Graphiti, where do telemetry signals go, and what comes in Stage 01?"

## Why this stage is documentation-only

Writing documentation before code is the cheapest opportunity to find architectural mistakes. The cost of changing an ADR is one PR; the cost of changing a deployed Helm chart is a migration. We pay the cheap cost first.

This is also the moment to lock in the language. The terms "per-app isolation," "platform initialization," "workload separation," "namespace boundary" are introduced here; they are used consistently from Stage 01 onward. The terms "tenancy" and "bootstrap" are deliberately not used.

## Next stage

Stage 01 provisions the local K3s cluster via k3d and installs ArgoCD. See `docs/stages/STAGE-01-cluster-provisioning/README.md`.

## See also

- `docs/overview/00-platform-overview.md` — the orientation document.
- `docs/adr/README.md` — the ADR index.
- `docs/layers/` — the seven-layer documentation set.
- `FLOW.mmd` — the documentation deliverable map.
