# platform/observability — MVP observability (`ai-observability` namespace)

Prometheus + Grafana for the kagent MVP. Conforms to `infra-code/SPEC.md` §4 (DNS/ports) and
§11 (observability). **Deviation (SPEC §11/§15):** docs mandate Alloy → LGTM-P (ADR-0006); the MVP
uses plain Prometheus + Grafana as a deliberate, reversible prototype shortcut.

## Components

| File | Resource | DNS:port | Image |
|---|---|---|---|
| `prometheus.yaml` | Deployment + Service + ConfigMap + SA/ClusterRole/Binding | `prometheus.ai-observability:9090` | `prom/prometheus:v2.54.1` |
| `grafana.yaml` | Deployment + Service + datasource/provider ConfigMaps | `grafana.ai-observability:3000` | `grafana/grafana:11.2.0` |
| `dashboards/mvp-agent.json` | dashboard JSON (source of truth) | — | — |

`kustomization.yaml` bundles them and builds the dashboard ConfigMap
(`grafana-dashboard-mvp-agent`) directly from `dashboards/mvp-agent.json` via
`configMapGenerator` (sync-wave 1, SPEC §12).

## Prometheus

Scrapes `/metrics` per SPEC §11.

**Static target:**

| Job | Target | Notes |
|---|---|---|
| `agent-backend` | `agent-backend.ai-platform:8000` | FastAPI `/metrics` |
| `prometheus` | `localhost:9090` | self-scrape / scrape health |

**Pod-discovery jobs** (`kubernetes_sd_configs`, role: pod) for endpoints whose port/path vary by
chart version — they keep pods annotated `prometheus.io/scrape=true` and honour
`prometheus.io/path` / `prometheus.io/port`:

| Job | Namespace | Notes |
|---|---|---|
| `kong` | `ai-gateway` | Kong `prometheus` plugin on the status listener (`:8100`) |
| `kagent` | `kagent` | kagent control plane (chart-version-dependent metrics endpoint) |

The two MCP servers (`mcp-web-search:3001`, `mcp-graphiti-memory:3002`) expose ONLY `/mcp` — no
`/metrics` — so per SPEC §16 they are **intentionally not scraped**; MCP activity is observed
indirectly via the agent-backend A2A metric.

**RBAC:** a `prometheus` ServiceAccount + ClusterRole (get/list/watch on
pods/services/endpoints/nodes) + binding, required for the k8s service discovery.

TSDB is on an `emptyDir` (3-day retention) — ephemeral, MVP-only.

## Grafana

- **Datasource** (`grafana-datasources`): Prometheus at `http://prometheus.ai-observability:9090`,
  `uid: prometheus`, default. The dashboard panels reference that exact uid.
- **Dashboard provider** (`grafana-dashboard-provider`): loads JSON from
  `/var/lib/grafana/dashboards` (mounted from the generated dashboard ConfigMap).
- **Dashboard `mvp-agent`** panels: request rate by service, latency p50/p95 (agent-backend),
  5xx error rate, A2A call outcomes, and a scrape-target up/down stat row.
- Anonymous Viewer is enabled (no login) for `make smoke`; basic-auth login form disabled.

> Panel queries use the SPEC §16 app-prefixed metric names: `agent_backend_requests_total`,
> `agent_backend_request_latency_seconds_bucket`, `agent_backend_a2a_calls_total{outcome}`. The
> agent-backend `/metrics` exporter MUST emit exactly these names.

## Security

Both run **non-root** with read-only root filesystems, drop all capabilities, no privilege
escalation, `RuntimeDefault` seccomp. Image tags pinned (no `:latest`).

## Dependencies (out of scope, wave 0)

`ai-observability` namespace + its default-deny NetworkPolicy are created at platform stand-up.
Prometheus carries its own `prometheus-allow-egress` policy (DNS + the SPEC §4 scrape ports + the
K8s API for service discovery). The **target** namespaces must allow ingress from `ai-observability`
on those scrape ports (`agent-backend:8000`, `kong:8100`, `kagent`); those allow-edges live with the
respective components, not here.

## Validate

```bash
kustomize build infra-code/platform/observability | kubeconform -strict -summary
python3 -c "import json; json.load(open('dashboards/mvp-agent.json'))"
```
