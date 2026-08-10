# ADR-0006: Grafana Alloy as the unified telemetry collector; LGTM-P + Langfuse as backends

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

The platform must collect metrics, logs, traces, and continuous profiles from a dozen services and emit them to backends that support both ops (SRE) and AI engineering (prompt-trace) workflows. Three architectures were considered:

1. Vanilla OpenTelemetry Collector + kube-prometheus-stack (Prometheus server + node-exporter + kube-state-metrics) + Promtail + a profiling agent. Four collectors to operate.
2. **Grafana Alloy** as a single unified collector that is itself an OTel Collector distribution, with native pipelines for OTLP, Prometheus scrape, Loki push, Tempo OTLP, and Pyroscope profiling — all in one binary with built-in clustering for production scale.
3. A commercial unified agent (Datadog Agent, New Relic Infra). Rejected on the self-hosting constraint.

Grafana Alloy reached v1.0 in 2024 and is the merger of the former Grafana Agent codebase with the OpenTelemetry Collector. Alloy is 100% OTLP-compatible — services emit OTLP as they would to any collector. The difference is on the receiving side: Alloy ships native Prometheus scraping (so there is no separate `prometheus-agent`), native Loki push (so there is no Promtail), and native Pyroscope receivers, all configurable via Alloy's programmable component syntax with a local web UI at port 12345 for live pipeline inspection.

OpenTelemetry remains the *wire protocol* that platform services emit. The decision is which **collector implementation** receives it. Replacing two collectors and a Prometheus server with one Alloy install is a material operational simplification.

## Decision

The platform observability architecture:

1. Every service emits OpenTelemetry traces, metrics, logs, and (optionally) Pyroscope profiles. OTLP is the wire protocol. GenAI semantic conventions (`gen_ai.*`) are mandatory on LLM-emitting spans.
2. A single **Grafana Alloy** install is the unified collector. It receives OTLP, scrapes Prometheus exporters (including kube-state-metrics and node-exporter, both of which Alloy ships natively), pushes logs to Loki, and pushes profiles to Pyroscope.
3. Alloy runs as a 3-replica clustered DaemonSet-plus-StatefulSet (clustered mode for scrape sharding) under namespace `ai-observability`.
4. Alloy fans out to:
   - **Mimir** via Prometheus remote-write — metrics backend.
   - **Loki** via Loki push — logs backend.
   - **Tempo** via OTLP — traces backend.
   - **Pyroscope** via its native protocol — profiles backend.
   - **Langfuse v3** via OTLP — GenAI prompt traces, eval scores, AI Observability dashboards.
5. **Grafana** is the visualization plane for ops; **Langfuse** is the visualization plane for AI engineering.
6. PII handling: Alloy's OTel processors (the same OTTL processors that ship in the vanilla Collector) redact patterns in span attributes and drop or redact span events (`gen_ai.content.prompt`, `gen_ai.content.completion`) per workload policy before export.
7. We retain the reference workload's two custom Prometheus histograms (`llm_inference_duration_seconds`, `llm_stream_duration_seconds`). Alloy scrapes them directly; no Prometheus server in between.

Components we do *not* deploy as a result of this decision:

- Vanilla `otel-collector` Helm chart — Alloy is the OTel Collector distribution.
- `kube-prometheus-stack` Helm chart — Alloy scrapes the same endpoints; alerting moves to Mimir's ruler.
- `promtail` DaemonSet — Alloy reads container logs.
- `prometheus-agent` — same reason.

## Consequences

Positive:

- One collector to operate, one config language, one upgrade cadence. Approximately a 70% reduction in observability-component count.
- Built-in Alloy clustering for production scale (scrape sharding, agentless HA).
- Continuous profiling is in scope from day one via Pyroscope — adds CPU and memory flame graphs over time without operating a separate profiling agent.
- 100% OTLP-compatible — if we ever need to switch to a different collector, services do not change.
- A live web UI for pipeline debugging (port 12345) is operationally valuable.
- Mimir-native alerting via its ruler replaces Alertmanager-on-Prometheus, with the same Prometheus rule syntax.

Negative:

- Alloy uses Grafana's component-based configuration syntax rather than the OTel Collector YAML format. Engineers familiar with the vanilla Collector must learn it. We mitigate by maintaining annotated example configs under `platform/L7-observability/alloy/`.
- Alloy is a *Grafana-flavored* OTel distribution. Coralogix and other vendors have argued this constitutes soft vendor lock-in via the configuration syntax. We accept this because we already chose the LGTM-P backend stack; the configuration coupling is downstream of a backend decision we already made.
- Some niche OTel-contrib receivers and processors are slower to land in Alloy than in vanilla Collector. We will pin to recent Alloy versions and contribute back if we hit a gap.

Neutral:

- All five backends (Mimir, Loki, Tempo, Pyroscope, Langfuse) ship Helm charts that work on K3s without modification.

## Alternatives considered

- **Vanilla OTel Collector + kube-prometheus-stack + Promtail + separate profiling agent**: rejected because of operational overhead (four agents) versus Alloy's one.
- **OTel Collector with the Prometheus receiver**: workable but lacks the native Prometheus scrape ergonomics, native Loki push, and native Pyroscope support. Alloy is purpose-built for the LGTM-P backend.
- **Grafana Cloud (managed)**: rejected on the self-hosting constraint.
- **Langfuse-only (no LGTM-P stack)**: rejected because Langfuse is not a general-purpose metrics or log store; SREs need Grafana over Mimir/Loki/Tempo for infra observability.
- **OpenInference instead of OpenTelemetry GenAI semantic conventions**: rejected because OTel GenAI is now the de facto standard with broad vendor coverage; OpenInference has been narrowing in scope through 2026.

## References

- Grafana Alloy product page: https://grafana.com/oss/alloy-opentelemetry-collector/
- Alloy announcement (Grafana Labs, GrafanaCON 2024): https://grafana.com/blog/2024/04/09/grafana-alloy-opentelemetry-collector-with-prometheus-pipelines/
- Alloy v1.0 release: https://github.com/grafana/alloy/releases/tag/v1.0.0
- OTel Collector vs Alloy comparison (February 2026): https://oneuptime.com/blog/post/2026-02-06-compare-opentelemetry-collector-vs-grafana-alloy/view
- OpenTelemetry GenAI conventions (May 2026): https://opentelemetry.io/blog/2026/genai-observability/
- Langfuse self-hosting on Kubernetes: https://langfuse.com/self-hosting/deployment/kubernetes-helm
- PII redaction guidance: https://maketocreate.com/opentelemetry-genai-tracing-ai-agents-without-leaking-pii/
- Coralogix critique of Alloy soft lock-in (June 2025), informing the negative-consequences section: https://coralogix.com/blog/the-grafana-alloy-dilemma/
