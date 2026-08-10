# Stage 09 — Tools and Sandbox (L5)

## Goal

Provision the CubeSandbox cluster on KVM-capable nodes; register RuntimeClass cube; stand up `mcp-registry` and `mcp-sandbox-runner`; implement the three reference tools (`web-search`, `doc-search`, `code-exec`).

## Depends on

Stage 07.

## Deliverables

- CubeSandbox install at `platform/cluster/*/cube-pool/` with CubeMaster, Cubelet, CubeProxy, CubeVS, CubeShim deployed.
- `RuntimeClass cube` registered.
- `services/L5-tooling-integration/mcp-registry/` and `mcp-sandbox-runner/` deployed.
- Tool manifests in `shared/proto/mcp/`.
- Reference tools under `tools/` packaged as sandbox templates.

## Non-goals

- No long-lived sandboxed pods yet; this stage focuses on per-call invocation.

## Acceptance criteria

1. `E2B_API_URL` pointed at CubeMaster, a code-exec call returns within deadline.
2. Sandbox cold start p99 measured under 200 ms.
3. Egress policy enforced: a tool not declaring network access cannot reach the internet.
4. Audit events landing in ClickHouse.

## Next stage

Stage 10 (A2A) and stage 12 (Evaluation gets real tool-call traces).
