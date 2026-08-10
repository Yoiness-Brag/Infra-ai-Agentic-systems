# L7 — Observability

Complete observability + evaluation stack. Per ADR-0006, the platform deploys Grafana Alloy as the *only* collector — it replaces vanilla OTel Collector, kube-prometheus-stack, Promtail, and a standalone profiling agent.

```mermaid
flowchart TB
    SVCS[Services L1–L6] -->|OTLP| ALLOY[Grafana Alloy<br/>3-replica unified collector]
    ALLOY --> MIMIR[(Mimir<br/>metrics + Ruler)]
    ALLOY --> LOKI[(Loki<br/>logs)]
    ALLOY --> TEMPO[(Tempo<br/>traces)]
    ALLOY --> PYR[(Pyroscope<br/>profiles)]
    ALLOY --> LFW[Langfuse v3<br/>GenAI spans]
    GRAF[Grafana dashboards] --> MIMIR
    GRAF --> LOKI
    GRAF --> TEMPO
    GRAF --> PYR
    LFW --> CH[(ClickHouse)]
    EVS[eval-svc] -->|read traces / write scores| LFW
```

## Contents

| Folder | Role |
|---|---|
| `alloy/` | Grafana Alloy unified collector (clustered, 3-replica) |
| `mimir/` | Mimir metrics store + Mimir Ruler for alerts |
| `loki/` | Loki logs store |
| `tempo/` | Tempo traces store |
| `pyroscope/` | Pyroscope continuous-profile store |
| `langfuse/` | Langfuse v3 (Web + Worker) self-hosted |
| `grafana-dashboards/` | JSON dashboards loaded via Grafana sidecar |

## References

- Layer specification: `docs/layers/L7-observability-reliability/README.md`.
- Decision rationale: `docs/adr/0006-observability-alloy-lgtmp-langfuse.md`.
- Harness engineering doctrine: `docs/protocols/harness-engineering.md`.
- OTel GenAI semconv: `docs/protocols/otel-genai-semconv.md`.
