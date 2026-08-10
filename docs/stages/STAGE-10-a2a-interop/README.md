# Stage 10 — A2A Interop

## Goal

Stand up `a2a-adapter`. Generate Agent Cards from kagent Agent CRDs. Route inbound A2A traffic through Kong. Implement outbound A2A client used by L3 services.

## Depends on

Stage 06, Stage 07.

## Deliverables

- `services/L5-tooling-integration/a2a-adapter/` deployed.
- `/.well-known/agent.json` served per workload.
- JSON-RPC 2.0 `tasks/send`, `tasks/sendSubscribe`, `tasks/cancel` endpoints.
- A2A schema under `shared/proto/a2a/`.
- A pair-test: the reference workload delegates a subtask to a second instance of itself via A2A and reconciles the result.

## Non-goals

- No federation registry; peer discovery is out-of-band for now.

## Acceptance criteria

1. Agent Card published and validates against the A2A schema.
2. Inbound and outbound tasks measured under the SLO targets.
3. Audit events distinguish A2A inbound vs L1-originated requests.

## Next stage

Stage 11 (Governance) tightens A2A peer policy.
