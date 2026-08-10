# Stage 03 — Observability (L7 stack)

## Goal

Stand up the full observability plane before any agent code runs, so that every later stage emits into a working system. Install Grafana Alloy as the unified collector (replacing the four-agent vanilla pattern), the LGTM-P backend stack (Loki, Grafana, Tempo, Mimir, Pyroscope), Langfuse v3, and cert-manager (cert-manager is L6 but L7 depends on TLS issuance).

## Depends on

Stage 01 (cluster) and Stage 02 (data plane for Langfuse stores: ClickHouse, Postgres, Redis, MinIO).

## Deliverables

- **Grafana Alloy** Helm install at `platform/L7-observability/alloy/`. Clustered, 3-replica. Configured to receive OTLP, scrape Prometheus exporters natively, push Loki, push Pyroscope, fan out to Mimir / Loki / Tempo / Pyroscope / Langfuse.
- **Mimir** Helm install with the Mimir Ruler enabled for alerting (replaces Alertmanager-on-Prometheus).
- **Loki** Helm install.
- **Tempo** Helm install.
- **Pyroscope** Helm install (new in this revision — continuous profiling from day one).
- **Grafana** Helm install with the ported `llm_latency.json` from the reference workload, per-layer RED dashboard placeholders, and the Grafana AI Observability dashboards.
- **Langfuse v3** (Web + Worker) wired to ClickHouse + Postgres + Redis + MinIO from Stage 02.
- **cert-manager** with ClusterIssuer for Let's Encrypt staging.
- Alloy OTTL processors configured for PII redaction and per-workload sampling.

## Non-goals

- No platform services emit yet; eval-svc is Stage 12. This stage stands up the observability backbone; it does not have agents to observe.
- No alerting rules in Mimir Ruler beyond the platform-self-monitoring defaults. Workload-specific rules come with the workload.

## Acceptance criteria

1. Grafana shows live metrics from kube-state-metrics scraped by Alloy.
2. Langfuse Web UI is reachable; a manual OTLP test trace lands.
3. Alloy's OTTL processor scrubs synthetic PII patterns out of test telemetry.
4. cert-manager issues a valid certificate to the Langfuse ingress.
5. Pyroscope receives a profile from a synthetic test pod.
6. Mimir Ruler evaluates a sample alert rule and routes a test alert.

## Next stage

Stage 05 (Gateway — Kong begins emitting OTLP through Alloy), Stage 11 (Governance — OTTL pipeline becomes authoritative), Stage 12 (Evaluation — eval-svc lands and reads/writes Langfuse).
