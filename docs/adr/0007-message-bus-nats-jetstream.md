# ADR-0007: NATS JetStream as the east-west message bus

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

The orchestrator-worker pattern (Anthropic's published blueprint, 90.2% measured uplift over single-agent) requires the lead to publish subtasks and many workers to consume in parallel. The Excalidraw shows multiple parallel "Agentic-Flow" workers fanning out from a router. We need a durable message bus with the following properties:

- At-least-once delivery with redelivery on consumer NACK or timeout.
- Request-reply semantics for tool calls that need a synchronous-looking response.
- Sub-millisecond latency in the typical case (we are below 1 M events/sec, so we are not throughput-bound).
- Native Kubernetes deployment story.
- Ability to scale consumers on lag, not CPU.
- A single binary or Helm chart, not a multi-service stack.

The three serious 2026 candidates:

- **Apache Kafka**: dominant in data-pipeline territory. Designed for trillions of messages/day, long retention, exactly-once stream processing. Operationally heavy (Zookeeper or KRaft, partition planning, schema registry). Throughput beyond our needs.
- **Apache Pulsar**: separates compute (brokers) from storage (BookKeeper), good multi-tenancy. Less mature ecosystem than Kafka, more components than NATS.
- **NATS JetStream**: single binary, sub-ms latency, pub-sub + request-reply + durable streams + key-value buckets in one. K8s-native, KEDA scaler exists. Designed for microservice communication.

Below ~1M events/sec, the consensus benchmark guide is: NATS JetStream is the K8s-microservice default; Kafka is the data-pipeline default. We are squarely in the microservice case.

## Decision

We use **NATS JetStream** as the platform's east-west message bus. Topology: a 3-replica JetStream cluster Helm-deployed under namespace `ai-platform`, with R3 streams (3-replica writes) for all production subjects.

Subject design:

- `agents.subtask.<session_id>` — orchestrator-to-worker subtask dispatch.
- `agents.result.<session_id>` — worker-to-orchestrator results.
- `tools.invoke.<tool>.<session_id>` — tool invocation requests when async dispatch is appropriate.
- `memory.ingest.<workload_app>` — memory write events from any service for asynchronous Graphiti ingestion.
- `audit.<service>.<action>` — audit events bound for ClickHouse via the Langfuse Worker.

Each subject's contract lives in `shared/proto/asyncapi/` as an AsyncAPI specification.

We use **KEDA** with the NATS JetStream scaler to autoscale `agent-worker` on consumer lag (not CPU).

## Consequences

Positive:

- Single binary, simple operational model.
- Sub-millisecond latency for the request-reply pattern.
- KEDA scaler is a natural fit for orchestrator-worker fan-out.
- Native K8s Helm chart, no Zookeeper or BookKeeper to operate.

Negative:

- At-least-once delivery (the standard JetStream guarantee) forces every consumer to be idempotent. We accept this and document the pattern: every async edge carries a UUIDv7 idempotency key; every consumer maintains a dedup table in Redis with TTL > redelivery window.
- JetStream is not as battle-tested as Kafka at extreme scale. We are far from that scale; if we ever approach it, the migration cost to Kafka is a known quantity.
- Subjects do not have a schema enforcement layer like Kafka's Schema Registry. We mitigate with AsyncAPI specs in `shared/proto/asyncapi/` and CI validation.

Neutral:

- The KEDA scaler is in the official keda-core-contrib repository and stable.

## Alternatives considered

- **Apache Kafka**: rejected because operational overhead is unjustified at our event volume; we will revisit if and when we have data-pipeline use cases.
- **Apache Pulsar**: rejected because of higher component count (brokers + BookKeeper + ZooKeeper or BookKeeper-only modes), less mature ecosystem.
- **Redis Streams**: rejected because we already use Redis for short-term memory and cache; coupling the platform's primary message bus to the same Redis instance is an availability anti-pattern.
- **RabbitMQ**: rejected because no first-class K8s Helm story comparable to NATS, no KEDA scaler integration as clean, and we do not need AMQP semantics.

## References

- NATS vs Kafka vs Redis Streams 2026: https://dev.to/young_gao/real-time-event-streaming-kafka-vs-redis-streams-vs-nats-in-2026-34o1
- Event-driven architecture 2026: https://encore.cloud/resources/event-driven-architecture
- KEDA NATS JetStream scaler: https://keda.sh/docs/2.14/scalers/nats-jetstream/
