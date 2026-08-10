# Layer 6 — Safety, Policy and Governance

## Purpose

L6 is the cross-cutting enforcement plane. It does not host its own request flow; instead, it embeds enforcement points into L1 through L5 and emits the audit trail that closes the loop. L6 is the answer to "did this action comply with policy?" — at admission, at the perimeter, at telemetry egress, and at the audit ledger.

L6 is **defense in depth**. No single enforcement point is trusted. Every decision is recorded.

## Components

**Platform**:

| Component | Purpose |
|---|---|
| **OPA Gatekeeper** | Kubernetes admission controller. Constraint Templates and Constraints reject non-compliant resources before they are persisted. |
| **cert-manager** | TLS certificate issuance and rotation. Provides per-service mTLS where needed. |
| **OTel Collector OTTL processors** | Redact PII patterns from telemetry attributes and span events before export. |
| **ClickHouse audit table** | The append-only ledger of policy-relevant events. Retained 90 days by default. |

**Enforcement points** (across other layers, governed by L6):

| Layer | Enforcement |
|---|---|
| L1 (Kong) | `ai-prompt-guard` (prompt-injection), `request-transformer` (sanitization), `jwt` (auth), `ai-rate-limiting-advanced` (quota) |
| L3 (kagent) | HITL gates on flagged tools; Agent CRD field validation; per-namespace NetworkPolicies |
| L5 (mcp-sandbox-runner) | Tool allowlist enforcement per Agent CRD; manifest schema validation; sandbox egress policy via CubeVS |
| L7 (OTel Collector) | OTTL processors redact PII before export to backends |

## Contracts

### Admission policies (OPA Gatekeeper)

The platform ships the following constraints (sources under `platform/L6-governance/opa-gatekeeper/policies/`):

| Constraint | Effect |
|---|---|
| `RequireResourceLimits` | Reject any Deployment or Pod that does not declare CPU and memory `requests` and `limits`. |
| `DisallowLatestImageTag` | Reject images tagged `:latest`. |
| `DisallowPrivilegedContainers` | Reject containers with `securityContext.privileged: true` (except in `cube-system`). |
| `RequireCubeRuntimeClassInTools` | Reject pods in `tools-*` namespaces that do not specify `runtimeClassName: cube`. |
| `RequireAgentResourceBounds` | Reject Agent CRDs without `resources.requests` and `resources.limits`. |
| `RequireNetworkPolicy` | Reject workload namespaces without a default-deny NetworkPolicy. |
| `RequireOTelSidecarOrSDK` | Warn (audit-mode) when a workload pod is missing OTel instrumentation. |

### Telemetry redaction (OTTL)

The OTel Collector processor pipeline includes:

- An OTTL processor that scans span attributes and span events for patterns matching email, phone number, SSN, credit-card-like sequences, and configured per-workload patterns; replaces matches with `[REDACTED]`.
- A second processor that drops span events tagged `gen_ai.content.prompt` and `gen_ai.content.completion` when the workload's policy disables prompt-body export.
- A sampling processor that retains 100% of error spans, 100% of HITL events, and 5% of routine traces by default.

### Audit trail (ClickHouse)

The Langfuse Worker writes prompt traces and eval scores to ClickHouse. The platform additionally writes a separate `platform_audit` table from the OTel Collector's audit-event branch. Schema lives in `platform/L7-observability/langfuse/audit-schema.sql`.

| Field | Type | Source |
|---|---|---|
| `ts` | DateTime64(9) | event time |
| `workload_app` | LowCardinality(String) | from headers |
| `actor` | String | JWT `sub` or service identity |
| `action` | LowCardinality(String) | one of `tool_invoke`, `hitl_pending`, `hitl_approved`, `hitl_denied`, `policy_denied`, `egress_blocked`, ... |
| `target` | String | tool id, agent name, etc. |
| `details_json` | String | redacted JSON |
| `trace_id` | String | OTel trace id |

### RBAC layers

L6 enforces RBAC at three independent layers:

1. **Kong consumer / key** per app. Determined by the JWT `iss` claim; bound to per-app rate-limit configuration.
2. **Kubernetes RBAC** per namespace. ServiceAccounts in workload namespaces cannot read across.
3. **kagent CRD-level** per agent. Each Agent CRD's tool allowlist is final; mcp-sandbox-runner re-checks it on every call.

## Distributed-system properties (L6 commitments)

- **Default-deny** at every enforcement point. Tools that need network egress declare it explicitly; pods that need elevated permissions declare them in CRDs that OPA validates.
- **Append-only audit** in ClickHouse with TTL-based retention. Deletes happen only via the retention policy, never via application code.
- **No PII in attribute strings**. Prompts go in span events so they can be dropped or redacted as data; not in attributes, which leak into label cardinality.
- **Policy is in Git**. Every constraint is a YAML manifest under `platform/L6-governance/`. Changes go through PR review.

## Service-level objectives

| SLO | Target |
|---|---|
| OPA Gatekeeper admission decision latency p99 | < 100 ms |
| OTTL processor added latency at OTel Collector p99 | < 5 ms |
| Audit event write to ClickHouse p99 (async via Langfuse Worker) | < 5 s |
| False positive rate on PII redaction patterns | tracked, target < 1% on synthetic corpus |

## Out of scope

- Identity issuance. Per-app JWT issuers live outside the platform.
- Model-side hallucination detection. That belongs to L7 (`eval-svc`).
- Tool execution itself. The sandboxing is L5; L6 only enforces the policy that says which tools may run.

## See also

- ADR-0006: Observability and PII redaction at the OTel Collector.
- ADR-0009: RuntimeClass cube enforced via OPA Gatekeeper.
- `FLOW.mmd` — the four enforcement points highlighted on the request path.
- `components.md` — full constraint catalog; OTTL processor configuration.
- `runbook.md` — add a new admission policy, debug a redaction false positive, query the audit ledger.

## Status

Documentation contract in place at Stage 00. cert-manager and OPA Gatekeeper land at Stage 03. OTTL redaction lands at Stage 03. Audit ledger lands at Stage 11.
