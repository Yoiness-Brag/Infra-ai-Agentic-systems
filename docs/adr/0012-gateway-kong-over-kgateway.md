# ADR-0012: Replace kgateway with Kong AI Gateway at the request perimeter

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

ADR-0011 adopted kagent as the base platform. kagent ships with **kgateway** (the Envoy-based gateway formerly known as Gloo, now a CNCF project by Solo.io) as the default ingress.

The Excalidraw design and the requirements list specify an API gateway with:

- Multi-LLM provider routing across OpenAI, Anthropic, Gemini, GLM, Kimi 2, plus local Ollama, with semantic routing and cross-provider failover.
- Per-app JWT authentication with per-app rate limits at 10 requests per second.
- Semantic caching of LLM responses.
- PII sanitization and prompt-injection guardrails at the perimeter.
- Token-based rate limiting (cost-aware, not just request-count-aware).

kgateway is a capable Kubernetes Gateway API implementation. It has an AI Gateway feature set, but the LLM-specific plugin coverage in 2026 is less mature than Kong's.

Kong has shipped LLM-specific functionality continuously since Gateway 3.6 (February 2024) and is on a 2026 roadmap focused on agentic governance:

- **ai-proxy** and **ai-proxy-advanced** plugins: multi-provider routing, semantic load balancing, failover, circuit breaker (`ai-proxy-advanced` adds load balance, failover and circuit breaker for semantic routing per the Kong changelog).
- **ai-semantic-cache** plugin: vector-store-backed semantic cache (Redis, Postgres pgvector, or external store).
- **ai-rate-limiting-advanced** plugin: token-based rate limiting (counts input + output tokens, not just requests).
- **AI guardrails** plugins: PII sanitization, prompt-injection detection.
- **MCP plugin support** in Kong AI Gateway, including OpenTelemetry semantic conventions for AI, MCP, and A2A traffic.
- A2A traffic governance announced in Kong's March 2026 Agentic Era roadmap.

## Decision

We replace kgateway with **Kong AI Gateway (OSS)** as the request perimeter. kgateway is uninstalled in the kagent base; Kong AI Gateway is installed via its official Helm chart with the AI plugin bundle enabled.

Routes for agentic workloads land at Kong. Kong routes them to the appropriate workload Service in the appropriate Kubernetes namespace. Kong is also the egress point for outbound LLM calls via `ai-proxy-advanced`.

Kong-and-kagent contract: kagent's internal control-plane traffic does not go through Kong; it stays inside the cluster as native K8s Service-to-Service calls. Only the workload's user-facing endpoints front Kong.

## Consequences

Positive:

- The Excalidraw and requirements specifications are met without bespoke logic. Each plugin maps directly to a stated requirement.
- Single ADR-locked decision avoids ongoing debate about which gateway to use per workload.
- Token-based rate limiting addresses the agentic cost-control story that request-count limits do not.
- Semantic caching at the gateway reduces LLM cost without modifying agent code.
- A2A and MCP-aware governance plugins are upstream-maintained.

Negative:

- We diverge from the kagent default. Upstream kagent docs assume kgateway; we maintain a small set of platform notes documenting the Kong substitution.
- Kong is a Lua-on-Nginx data plane; engineers familiar with Envoy must learn it.
- Some Kong Enterprise-only features tempt teams to upgrade; we document which features are OSS-only in `platform/L1-gateway/kong/README.md`.

Neutral:

- Both Kong and kgateway run as standard K8s Deployments behind a Service. Operational footprint is similar.

## Alternatives considered

- **Keep kgateway**: rejected because the AI-specific plugin coverage does not match Kong's in 2026, and our requirements list is explicit on the plugin set.
- **Both Kong and kgateway side by side**: rejected because two ingresses to govern is more work and more confusion, with no benefit.
- **Cloud-managed AI gateway (Cloudflare AI Gateway, AWS Bedrock gateway)**: rejected because self-hosting is a stated platform constraint.
- **Bifrost (Go-based AI gateway by Maxim AI)**: considered, but Kong has broader ecosystem maturity, longer track record, and direct compatibility with the existing Kong API Gateway investment any user already running Kong has.

## References

- Kong AI Gateway product page: https://konghq.com/products/kong-ai-gateway
- Kong AI Gateway developer docs: https://developer.konghq.com/ai-gateway/
- Kong Gateway changelog (semantic routing, circuit breaker, etc.): https://developer.konghq.com/gateway/changelog/
- Kong 2026 agentic roadmap: https://techbytes.app/posts/kong-ai-connectivity-agentic-stack-governance/
- kgateway feature set: https://kagent.dev/agents/kgateway-agent
