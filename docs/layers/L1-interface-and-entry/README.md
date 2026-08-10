# Layer 1 — Interface and Entry

## Purpose

L1 is how the outside world reaches an agentic workload running on this platform. Its job is to accept inbound HTTP and SSE traffic, authenticate the caller, enforce per-app quotas, sanitize input, route to the correct workload, and stream the response back. L1 is also the egress point for outbound LLM calls when the agent runtime chooses to route through it.

L1 is **thin and stateless**. It does not embed agent logic. It does not hold conversation state. It does not implement business rules. Its job is to be the safe, observable, governed boundary between the outside and L2.

## Components

The L1 implementation is a single component:

- **Kong AI Gateway** (Kong OSS 3.8+) installed via the official Helm chart, deployed in the `ai-gateway` namespace.

Plugins enabled, configured per route:

| Plugin | Purpose |
|---|---|
| `jwt` | Per-app JWT validation. Each app issues its own keys; the `iss` claim selects the per-app rate limit configuration. |
| `ai-rate-limiting-advanced` | Token-based rate limiting at 10 requests per second per app (Excalidraw spec), plus token-budget caps. |
| `ai-semantic-cache` | Embedding-similarity cache, backed by Redis with redis-vss. Cuts cost and latency for repeated near-duplicate prompts. |
| `ai-proxy-advanced` | Multi-LLM provider routing across OpenAI, Anthropic, Gemini, GLM, Kimi 2, Ollama. Semantic routing rules, cross-provider failover, circuit breaker. |
| `request-transformer` | Input sanitization (the Excalidraw "input sanitization" item). |
| `ai-prompt-guard` | Prompt-injection detection and policy enforcement. |
| `cors` | CORS handling for browser clients. |
| `prometheus` | Metrics export at `/metrics`. |
| `opentelemetry` | OTLP export of request spans with GenAI semantic conventions. |

Companion components owned by L1:

- **cert-manager** issues TLS certificates for the gateway's public endpoints. Lives in L6 (`platform/L6-governance/cert-manager/`) but is referenced from L1.
- **Ingress / LoadBalancer**: on k3d the gateway is exposed via host port; on K3s-on-VM via MetalLB; on AWS via the AWS Load Balancer Controller. Configurations live in `platform/cluster/*/`.

## Contracts

### Upstream contract (what L1 exposes to callers)

- **HTTPS endpoints** at `https://gw.<env>.platform.local/*`. SSE supported on streaming endpoints.
- **Authentication**: `Authorization: Bearer <JWT>`. JWTs are issued by per-app issuers; the platform does not issue user-facing JWTs.
- **Errors**: standard HTTP semantics. 401 on auth failure, 403 on policy denial, 429 on rate-limit exceed, 5xx on backend failure.
- **Headers returned**: standard rate-limit headers (`RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`), plus `X-Request-Id` for trace correlation.

### Downstream contract (what L1 consumes from L2)

- Routes traffic to L2 Services by Kubernetes Service DNS names. Path prefix selects the workload.
- Health checks via the standard `/health` endpoint on each backend Service.
- Streaming pass-through for SSE responses from `agent-orchestrator`.

## Service-level objectives

| SLO | Target |
|---|---|
| L1 availability | 99.9% (excluding planned maintenance) |
| L1 added latency (p50, non-cached) | < 5 ms |
| L1 added latency (p99, non-cached) | < 25 ms |
| Semantic cache hit ratio (steady state) | > 30% |
| Rate-limit accuracy | ±1 request per second across a rolling 60-second window |

## Inputs and outputs

- Reads: per-app key sets from Kong's database (Postgres), Redis for rate-limit counters and semantic cache.
- Writes: OTLP spans to the OTel Collector at `otel-collector.ai-observability:4317`.
- Failures bubble up to OpenTelemetry as spans with `error=true` and to Prometheus as counter increments.

## Out of scope

- Agent logic. Belongs to L3.
- Conversation memory. Belongs to L4.
- Tool sandboxing. Belongs to L5.
- Policy beyond perimeter sanitization and rate limiting. The deeper policy enforcement (admission, audit retention) belongs to L6.

## See also

- ADR-0012: Replace kgateway with Kong AI Gateway.
- `FLOW.mmd` — request flow through L1.
- `components.md` — exact Kong configuration shape.
- `runbook.md` — deploy, verify, rotate keys, debug failed auth.

## Status

Documentation contract is in place at Stage 00. Implementation lands at Stage 05.
