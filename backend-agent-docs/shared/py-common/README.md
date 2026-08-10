# shared/py-common/

Shared Python library imported by every service. Lifts the small, well-tested utilities from the reference workload's `app/common/` into a packageable shared module so each service does not reinvent them.

```mermaid
flowchart LR
    LOGS[logging.py<br/>structured JSON]
    OTEL[telemetry.py<br/>OTel SDK setup + GenAI semconv]
    MW[middleware.py<br/>FastAPI middleware: trace, auth, errors]
    NATS_C[nats_client.py<br/>connection + idempotency]
    SCHEMAS[schemas/<br/>shared Pydantic models]
    BACKOFF[backoff.py<br/>retry decorators]

    SVC[Every service] --> LOGS
    SVC --> OTEL
    SVC --> MW
    SVC --> NATS_C
    SVC --> SCHEMAS
    SVC --> BACKOFF
```

## Contract

Every service installs `py-common` as a dependency. Services do not reimplement logging, OTel SDK setup, NATS idempotency, or retry logic; they import from here.

## References

- Reference workload mapping: `docs/reference/upstream-repo-mapping.md`.
- OTel GenAI semconv: `docs/protocols/otel-genai-semconv.md`.
- Testing strategy: `docs/protocols/testing-strategy.md`.
