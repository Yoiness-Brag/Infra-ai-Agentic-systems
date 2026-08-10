# Stage 06 — kagent Base

## Goal

Install the kagent control plane via its official Helm chart, configure it to use Kong-fronted egress for LLM calls, and prove the CRD reconciliation loop with a placeholder Agent CRD.

## Depends on

Stage 01, Stage 03, Stage 04, Stage 05.

## Deliverables

- `platform/kagent-base/` Helm values.
- One placeholder Agent CRD that reconciles into a no-op pod.
- One placeholder ToolServer CRD pointing at a no-op MCP server.
- RBAC bindings so workload namespaces can apply Agent CRDs.

## Non-goals

- No real agents yet. Stage 07 brings the orchestrator and worker.

## Acceptance criteria

1. `kubectl get agents` shows the placeholder Agent Ready.
2. kagent controller logs are clean.
3. The placeholder pod has an OTel sidecar or SDK and emits a heartbeat span.

## Next stage

Stage 07 (real agents) and Stage 10 (A2A adapter).
