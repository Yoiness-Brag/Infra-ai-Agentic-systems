# Layer 7 — Observability, Reliability and Optimization

## Purpose

L7 captures every signal the platform emits, makes it available to operators and AI engineers, and runs the evaluation pipeline that scores production behavior. L7 closes the loop on both pillars of the seven-layer model: **system reliability and performance** (metrics, traces, logs, continuous profiles) and **workload behavior** (LLM-as-judge online scoring plus the harness composition documented in `docs/protocols/harness-engineering.md`).

L7 is the only layer that knows everything: it ingests from L1 through L6 uniformly via OpenTelemetry over OTLP, stores in the backends most appropriate for each signal type, and presents a single visualization plane for ops plus a single one for AI engineering.

## Components

**Platform** (observability stack):

| Component | Purpose |
|---|---|
| **Grafana Alloy** (clustered, 3-replica) | Unified telemetry collector. OpenTelemetry Collector distribution. Receives OTLP, scrapes Prometheus exporters natively, pushes Loki logs, pushes Pyroscope profiles. Applies OTTL processors (PII redaction, sampling). Single agent for the whole LGTM-P stack. |
| **Mimir** | Long-retention metrics backend. Receives Prometheus remote-write from Alloy. Includes Mimir Ruler for alerting (replaces Alertmanager-on-Prometheus). |
| **Loki** | Logs backend. Receives logs from Alloy. |
| **Tempo** | Traces backend. Receives OTLP from Alloy. |
| **Pyroscope** | Continuous profiling backend (CPU and memory flame graphs over time). Receives profiles from Alloy. |
| **Grafana** | Visualization. Dashboards include the ported `llm_latency.json` (reference workload), per-layer RED dashboards, Grafana AI Observability dashboards, the heuristics dashboard, the RAG-quality dashboard. |
| **Langfuse v3** (Web + Worker) | LLM-specific observability. Receives OTLP from Alloy. Hosts prompt traces, eval scores, datasets, prompt management. |
| **ClickHouse** | Langfuse v3 trace backend; also hosts `platform_audit` table. |
| **Postgres (Langfuse)** | Langfuse metadata. |
| **Redis (Langfuse)** | Langfuse v3 queue backing. |
| **MinIO** | S3-compatible object storage for Langfuse media uploads and offline eval artifacts. |

**Services**:

| Service | Purpose |
|---|---|
| **eval-svc** | Online LLM-as-judge scoring (the five metrics from the reference workload). Drives the harness composition: DeepEval, Promptfoo, Ragas, Inspect AI. Reads production traces from Langfuse; writes scores back. Runs CI gates against golden datasets. See `docs/protocols/harness-engineering.md`. |

## What we deliberately do *not* run

Per ADR-0006:

- No vanilla OTel Collector — Alloy *is* an OTel Collector distribution.
- No kube-prometheus-stack — Alloy scrapes the same endpoints.
- No Promtail — Alloy reads container logs.
- No standalone prometheus-agent — Alloy ships native Prometheus scraping.
- No standalone profiling agent — Alloy ships native Pyroscope.

## Contracts

### Instrumentation contract (what services emit)

Every platform service emits OTLP. Spans use OpenTelemetry GenAI semantic conventions where applicable (see `docs/protocols/otel-genai-semconv.md`). Required attributes on LLM-emitting spans:

- `gen_ai.system` (`openai`, `anthropic`, `gemini`, `ollama`, `kong-ai-proxy`)
- `gen_ai.operation.name` (`chat`, `embedding`, `completion`)
- `gen_ai.request.model`
- `gen_ai.response.model`
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.response.finish_reasons`

Required histograms:

- `gen_ai.client.operation.duration`
- `gen_ai.client.token.usage` (counter, direction=input|output)
- `gen_ai.client.error.count`

Prompts and completions as **span events** (`gen_ai.content.prompt`, `gen_ai.content.completion`), not attributes.

### Output channels

| Plane | Audience | Backed by |
|---|---|---|
| Grafana dashboards | SREs, platform engineers | Mimir, Loki, Tempo, Pyroscope |
| Langfuse UI | AI engineers, prompt engineers | ClickHouse, Postgres |
| `eval-svc` scorecards | AI engineers | Langfuse scores + DeepEval reports + Ragas reports + Inspect AI reports |

### Evaluation contracts

`eval-svc` exposes:

- `POST /eval/online/score` — score a single Langfuse trace synchronously against the five-metric rubric.
- A cron-triggered job that scores a sliding window of Langfuse traces.
- An invocation hook from CI that runs DeepEval, Ragas, Inspect AI suites on every change to `services/L3-agent-runtime/`, `services/L4-context-and-memory/`, `services/L5-tooling-integration/`, or `services/L7-evaluation/` paths.

Metric prompt sources are in `services/L7-evaluation/eval-svc/prompts/`, ported verbatim from the reference workload.

## Distributed-system properties (L7 commitments)

- **OpenTelemetry-native** wire protocol. Backends are pluggable; switching backends does not change services.
- **Alloy clustered** (3-replica) for scrape-shard HA and ingest HA.
- **Sampling honest**. 100% of error spans, 100% of HITL events, 100% of A2A inbound, 5% of routine traces by default. Per-workload override.
- **No prompt bodies in span attributes**. Only in events, only redacted, only when policy allows export.
- **Continuous profiling** in scope from day one via Pyroscope.
- **Evaluation runs both online and offline**. Production scoring of live traces plus offline regression suites in CI.

## Service-level objectives

| SLO | Target |
|---|---|
| Alloy added p99 latency | < 5 ms |
| Trace tail-sampling decision latency | < 1 s |
| Langfuse trace write end-to-end p99 | < 5 s |
| `eval-svc` online score latency p99 | < 3 s per trace |
| DeepEval offline suite CI runtime p99 | < 10 min per service |
| Ragas suite CI runtime p99 | < 15 min on golden datasets |
| Mimir metric retention | 30 days short, 1 year compacted |
| Loki log retention | 14 days |
| Tempo trace retention | 7 days full + 30 days sampled |
| Pyroscope profile retention | 7 days |
| ClickHouse audit retention | 90 days |

## Out of scope

- Reasoning. L7 observes; it does not decide.
- Storage of agent memory. Belongs to L4.
- Policy enforcement (other than PII redaction at the collector). Belongs to L6.

## See also

- ADR-0006: Grafana Alloy as the unified telemetry collector; LGTM-P + Langfuse as backends.
- `docs/protocols/otel-genai-semconv.md` — GenAI attribute requirements.
- `docs/protocols/harness-engineering.md` — the four-tool evaluation harness composition.
- `docs/protocols/testing-strategy.md` — per-component testing strategy that complements the eval harness.
- `FLOW.mmd` — telemetry pipeline and eval loop.
- `components.md` — Helm values references; Grafana dashboard catalog; eval prompt catalog.
- `runbook.md` — deploy Alloy + LGTM-P, install Langfuse v3, debug a missing trace, port a new DeepEval suite.

## Status

Documentation contract in place at Stage 00. Alloy, Mimir, Loki, Tempo, Pyroscope, Grafana, Langfuse v3 land at Stage 03. `eval-svc` and the full harness composition land at Stage 12.
