# Stage 11 — Governance (L6)

## Goal

Activate the full L6 enforcement set: OPA Gatekeeper constraints, the audit ledger in ClickHouse, the OTel Collector OTTL pipeline (already present from Stage 03 but now in audit-mode-off enforcement).

## Depends on

Stage 03, Stage 07.

## Deliverables

- OPA Gatekeeper Helm install + constraints under `platform/L6-governance/opa-gatekeeper/`.
- `platform_audit` ClickHouse table.
- Audit-event branch on the OTel Collector pipeline writing to Langfuse Worker.
- Per-app JWT issuer configuration as ConfigMaps + Secrets.

## Non-goals

- No automated policy generation; constraints are hand-authored YAML.

## Acceptance criteria

1. Constraints reject a deliberately non-compliant Agent CRD in CI.
2. Audit ledger receives events from every enforcement point.
3. A query over ClickHouse can reconstruct who-did-what for a given run.

## Next stage

Stage 12 closes the loop with evaluation.
