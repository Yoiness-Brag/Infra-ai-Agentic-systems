# shared/

Code and schemas reused across every service. Two subtrees: `py-common/` (shared Python library), `proto/` (schema-first contracts).

```mermaid
flowchart LR
    PY[py-common/<br/>logging, telemetry,<br/>middleware, NATS client]
    PROTO[proto/]
    PROTO --> OPEN[openapi/<br/>HTTP contracts]
    PROTO --> ASYNC[asyncapi/<br/>NATS subject contracts]
    PROTO --> A2A[a2a/<br/>Agent Card schemas]
    PROTO --> MCP[mcp/<br/>Tool manifest schemas]

    PY -.->|imported by| SVCS[All services]
    PROTO -.->|generates clients + validates| SVCS
    PROTO -.->|contract tests| CI[CI gates]
```

## References

- Testing strategy doctrine: `docs/protocols/testing-strategy.md` — describes how the contracts under `proto/` are enforced as contract tests in CI.
- OpenAPI: https://spec.openapis.org/
- AsyncAPI: https://www.asyncapi.com/
