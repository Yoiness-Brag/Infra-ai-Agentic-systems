# Implementation Stages

The platform is built in fifteen sequenced stages, from STAGE-00 (documentation foundation) through STAGE-14 (AWS production parity). Each stage has its own folder with a `README.md` describing what it delivers, an acceptance checklist, and where applicable a `FLOW.mmd`.

Stages are sequential because they have hard dependencies on each other; you cannot install Kong (Stage 05) before you have a K3s cluster (Stage 01). You cannot run the orchestrator-worker reference workload (Stage 07) before kagent is installed (Stage 06) and NATS is available (Stage 04).

## Sequence

| Stage | Title | Layers touched | Depends on |
|---|---|---|---|
| 00 | [Foundation](STAGE-00-foundation/README.md) | all (docs only) | — |
| 01 | [Cluster provisioning](STAGE-01-cluster-provisioning/README.md) | platform-wide | 00 |
| 02 | [Data plane](STAGE-02-data-plane/README.md) | L4 | 01 |
| 03 | [Observability](STAGE-03-observability/README.md) | L7 | 01 |
| 04 | [Message bus](STAGE-04-message-bus/README.md) | L2 | 01 |
| 05 | [Gateway](STAGE-05-gateway/README.md) | L1 | 01, 03 |
| 06 | [kagent base](STAGE-06-kagent-base/README.md) | L3 | 01, 03, 04, 05 |
| 07 | [Agent runtime](STAGE-07-agent-runtime/README.md) | L2, L3 | 06, port from reference workload |
| 08 | [Memory](STAGE-08-memory/README.md) | L4 | 02, 07 |
| 09 | [Tools and sandbox](STAGE-09-tools-and-sandbox/README.md) | L5 | 07 |
| 10 | [A2A interop](STAGE-10-a2a-interop/README.md) | L5 | 06, 07 |
| 11 | [Governance](STAGE-11-governance/README.md) | L6 | 03, 07 |
| 12 | [Evaluation](STAGE-12-evaluation/README.md) | L7 | 03, 07 |
| 13 | [CI/CD GitOps](STAGE-13-cicd-gitops/README.md) | platform-wide | all preceding |
| 14 | [AWS parity](STAGE-14-aws-parity/README.md) | platform-wide | 13 |

## Per-stage acceptance pattern

Every stage's `README.md` answers:

1. **Goal**: one paragraph.
2. **Deliverables**: bullet list of concrete artifacts produced.
3. **Non-goals**: what the stage deliberately does not do.
4. **Acceptance criteria**: numbered list of pass conditions.
5. **Next stage**: the immediate successor.

## Parallel work within a stage

Stages 02, 03, 04, and 05 can be worked in parallel once Stage 01 is done; they are independent. Stages 08 and 09 can run in parallel after Stage 07. Stage 14 can be started incrementally after Stage 13 is solid.

## See also

- `docs/overview/00-platform-overview.md` — what is built across all stages.
- `docs/adr/` — the decisions that shape every stage.
