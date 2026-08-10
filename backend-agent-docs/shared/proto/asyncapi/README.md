# shared/proto/asyncapi/

AsyncAPI 3.0 specifications for NATS subjects. The complement to OpenAPI for the event-driven side of the platform.

```mermaid
flowchart LR
    SPEC[asyncapi/{subject}.yaml] -->|generate| MODELS[Pydantic envelopes]
    SPEC -->|custom runner| RUN[shared/py-common/contract/<br/>AsyncAPI consumer-side validator]
    RUN -->|run on each PR| GATE[CI gate: producer ↔ consumer<br/>schema compatibility]
```

## Files (one per top-level subject hierarchy)

- `agents-subtask.yaml` — `agents.subtask.<session_id>`
- `agents-result.yaml` — `agents.result.<session_id>`
- `memory-ingest.yaml` — `memory.ingest.<workload_app>`
- `audit.yaml` — `audit.<service>.<action>`
- `dlq.yaml` — `*.dlq` parking subjects

## References

- AsyncAPI 3.0 specification: https://www.asyncapi.com/docs/reference/specification/v3.0.0
- NATS subject naming conventions: https://docs.nats.io/nats-concepts/subjects
- Decision rationale for NATS: `docs/adr/0007-message-bus-nats-jetstream.md`.
