# L2 — Orchestration and Control Plane

NATS JetStream (east-west bus) and KEDA (event-driven autoscaler).

```mermaid
flowchart LR
    L3[L3 — agent-orchestrator] -->|publish| NATS[NATS JetStream<br/>3-replica R3]
    NATS -->|deliver| L3W[L3 — agent-worker pool]
    L3W -->|publish result| NATS
    NATS -->|deliver result| L3
    NATS -.->|consumer lag| KEDA[KEDA scaler]
    KEDA -->|scale workers| L3W
```

## Contents

- `nats-jetstream/` — NATS Helm chart values, stream and consumer definitions.
- `keda/` — KEDA Helm install + `ScaledObject` templates.

## References

- Layer specification: `docs/layers/L2-orchestration-control-plane/README.md`.
- Decision rationale: `docs/adr/0007-message-bus-nats-jetstream.md`.
- NATS JetStream docs: https://docs.nats.io/nats-concepts/jetstream
- KEDA docs: https://keda.sh/docs/
