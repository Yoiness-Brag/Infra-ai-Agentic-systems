# NATS JetStream

The platform's only message bus. NATS JetStream (3-replica, R3 streams) carries every east-west event in the cluster per ADR-0007.

## What it owns

- Durable subjects: `agents.subtask.<session_id>`, `agents.result.<session_id>`, `memory.ingest.<workload_app>`, `audit.<service>.<action>`.
- At-least-once delivery with bounded redelivery; idempotency dedup at every consumer in Redis.
- Request-reply semantics for synchronous-looking tool calls.
- Consumer-lag signal for KEDA autoscaling of `agent-worker`.

## Why one bus

One stack per use case. NATS owns *every* east-west message; there is no parallel Kafka, no Redis Streams fallback, no RabbitMQ. The reasoning is in ADR-0007.

## Install and setup

Upstream: NATS Helm chart at https://github.com/nats-io/k8s.

```bash
helm repo add nats https://nats-io.github.io/k8s/helm/charts/
helm repo update

helm upgrade --install nats nats/nats \
  --version 1.x \
  --namespace ai-platform \
  --create-namespace \
  --values platform/L2-orchestration/nats-jetstream/values.yaml
```

Pinned `values.yaml`:
- `config.cluster.enabled: true`
- `config.cluster.replicas: 3`
- `config.jetstream.enabled: true`
- `config.jetstream.fileStore.pvc.size: 10Gi`
- `monitor.enabled: true` (Prometheus metrics)

Reconciled by ArgoCD in production.

## Flow

```mermaid
flowchart LR
    ORCH[agent-orchestrator] -->|publish agents.subtask.{sid}| NATS[NATS JetStream<br/>3-replica R3]
    NATS -->|deliver subtask| WRK[agent-worker pool<br/>KEDA-scaled]
    WRK -->|publish agents.result.{sid}| NATS
    NATS -->|deliver result| ORCH
    NATS -.->|consumer lag metric| KEDA[KEDA scaler]
    KEDA -->|scale workers| WRK
    SVC[any platform service] -->|publish memory.ingest, audit| NATS
    NATS -.->|OTLP from sidecar| ALLOY[Grafana Alloy]
```

## References

- NATS JetStream documentation: https://docs.nats.io/nats-concepts/jetstream
- NATS Helm chart: https://github.com/nats-io/k8s/tree/main/helm/charts/nats
- KEDA NATS JetStream scaler: https://keda.sh/docs/2.14/scalers/nats-jetstream/
- AsyncAPI specs for our subjects: `shared/proto/asyncapi/`
- Layer specification: `docs/layers/L2-orchestration-control-plane/README.md`
- Decision rationale: `docs/adr/0007-message-bus-nats-jetstream.md`

## Status

Helm values land at Stage 04.
