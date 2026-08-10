# shared/proto/openapi/

OpenAPI 3.1 specifications for HTTP services. One file per service.

```mermaid
flowchart LR
    SPEC[openapi/{service}.yaml] -->|generate| MODELS[Pydantic models<br/>service's src/schemas.py]
    SPEC -->|generate| CLIENTS[Typed clients<br/>for consumers]
    SPEC -->|schemathesis| TESTS[Property-based<br/>contract tests in CI]
    SPEC -->|served at runtime| DOCS[Service /docs endpoint]
```

## Files (one per public service)

- `kong-routes.yaml` — Kong route specifications.
- `agent-orchestrator.yaml` — `/chat/*` surface.
- `memory-svc.yaml` — `/retrieve`, `/episodes/*`, `/vectors/*`, `/session/*`.
- `mcp-registry.yaml` — `/tools`, `/manifests/*`.
- `mcp-sandbox-runner.yaml` — `/tools/invoke`.
- `a2a-adapter.yaml` — `/.well-known/agent.json`, `/a2a/tasks`.
- `rerank-svc.yaml` — `/rerank`.
- `session-svc.yaml` — `/sessions/{sid}/compact`.
- `eval-svc.yaml` — `/eval/online/*`, `/eval/offline/*`.

## References

- OpenAPI 3.1 specification: https://spec.openapis.org/oas/v3.1.0
- schemathesis: https://schemathesis.readthedocs.io/
