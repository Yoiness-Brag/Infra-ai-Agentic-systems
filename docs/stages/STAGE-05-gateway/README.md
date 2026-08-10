# Stage 05 — Gateway (L1)

## Goal

Install Kong AI Gateway, uninstall kgateway from the kagent base path, configure the plugin set (jwt, ai-rate-limiting-advanced, ai-semantic-cache, ai-proxy-advanced, ai-prompt-guard, request-transformer, prometheus, opentelemetry).

## Depends on

Stage 01, Stage 03.

## Deliverables

- Kong Helm install at `platform/L1-gateway/kong/`.
- ConfigMap-driven plugin set, with provider credentials in K8s Secrets.
- ServiceMonitor for the Prometheus scrape.
- OTLP exporter configured to point at the OTel Collector.

## Non-goals

- No backend routes defined yet. Routes are added in Stage 07 when the orchestrator exists.

## Acceptance criteria

1. Kong pods Ready.
2. `kong-status` shows all plugins loaded.
3. A test route through ai-proxy-advanced to a local Ollama works end to end.
4. Metrics and traces from Kong land in Mimir and Tempo.

## Next stage

Stage 06 (kagent base) and Stage 07 (agent runtime).
