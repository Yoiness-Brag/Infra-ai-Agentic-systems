# shared/proto/

Schema-first contracts. The single source of truth for inter-service interfaces. Code is generated from these (Pydantic models, OpenAPI clients) or validated against them (contract tests, AsyncAPI runners).

```mermaid
flowchart TB
    PROTO[shared/proto/]
    PROTO --> OPEN[openapi/<br/>HTTP service surfaces]
    PROTO --> ASYNC[asyncapi/<br/>NATS subject schemas]
    PROTO --> A2A[a2a/<br/>Agent Card + Task schemas]
    PROTO --> MCP[mcp/<br/>Tool manifest schemas]

    OPEN -->|generate| PYDANTIC[Pydantic models]
    OPEN -->|run| SCHEMATHESIS[schemathesis<br/>property-based tests]
    ASYNC -->|run| ASYNCAPI_RUN[Custom AsyncAPI runner]
    A2A -->|validate| A2A_SVC[a2a-adapter]
    MCP -->|load at startup| REG[mcp-registry]
```

## Contract

Any change to a schema in this directory triggers contract tests in CI. Producers and consumers are validated independently; a producer's PR is blocked if any consumer's schema cannot decode messages valid under the new spec.

## References

- Testing strategy doctrine: `docs/protocols/testing-strategy.md`.
- MCP specification: `docs/protocols/mcp.md`.
- A2A specification: `docs/protocols/a2a.md`.
- schemathesis: https://schemathesis.readthedocs.io/.
