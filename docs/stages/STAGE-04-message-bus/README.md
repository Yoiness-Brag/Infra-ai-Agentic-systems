# Stage 04 — Message Bus

## Goal

Install NATS JetStream (3-replica) and KEDA. Define the four NATS subjects with their AsyncAPI contracts.

## Depends on

Stage 01.

## Deliverables

- NATS Helm install at `platform/L2-orchestration/nats-jetstream/`.
- KEDA Helm install at `platform/L2-orchestration/keda/`.
- AsyncAPI specs in `shared/proto/asyncapi/` for: `agents.subtask.*`, `agents.result.*`, `memory.ingest.*`, `audit.*`.
- ScaledObject manifests targeting agent-worker (placeholder until Stage 07).

## Non-goals

- No producers or consumers yet.

## Acceptance criteria

1. NATS cluster Ready with 3 replicas.
2. `nats stream info` shows the four streams created.
3. KEDA installed and able to read JetStream consumer lag.

## Next stage

Stage 06 (kagent base) and Stage 07 (agent runtime).
