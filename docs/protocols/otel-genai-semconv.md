# OpenTelemetry GenAI Semantic Conventions

This document is the platform-specific implementation note for the OpenTelemetry GenAI semantic conventions. The conventions themselves are maintained by the OpenTelemetry Semantic Conventions Special Interest Group; this document covers how the platform applies them.

## Status

The `gen_ai.*` namespace has been moving from experimental to stable through 2025 and 2026. As of May 2026, Datadog ships native support; Langfuse, Honeycomb, OpenLLMetry, OpenLIT all map to the same namespace. The platform standardizes on `gen_ai.*` as the canonical instrumentation surface; vendor-specific SDKs may coexist but do not replace it.

## Required attributes

Every span that represents an LLM operation MUST carry:

| Attribute | Type | Example |
|---|---|---|
| `gen_ai.system` | string | `openai`, `anthropic`, `gemini`, `ollama`, `kong-ai-proxy` |
| `gen_ai.operation.name` | string | `chat`, `embedding`, `completion` |
| `gen_ai.request.model` | string | `gpt-4o-mini`, `claude-sonnet-4-5`, `llama3.2:3b` |
| `gen_ai.response.model` | string | model actually used (may differ from request after gateway routing) |
| `gen_ai.usage.input_tokens` | int | input token count |
| `gen_ai.usage.output_tokens` | int | output token count |
| `gen_ai.response.finish_reasons` | string[] | e.g., `["stop"]`, `["length"]`, `["tool_use"]` |

When the call originates from the Kong AI Gateway after multi-provider routing, `gen_ai.system` reflects the chosen provider, and a custom attribute `gen_ai.kong.route_decision` records the routing rule that fired.

## Prompts and completions

Prompts and completions are large, may contain PII, and are not labels. The platform standard:

- **Span events**, not span attributes:
  - `gen_ai.content.prompt` — event with `gen_ai.prompt` body.
  - `gen_ai.content.completion` — event with `gen_ai.completion` body.
- The OTel Collector OTTL processor pipeline can drop or redact these events per workload policy before export.
- Attributes carry only metadata (model, token counts, finish reasons), never the body.

## Metrics

Required histograms on every LLM-emitting service:

| Metric | Unit | Labels |
|---|---|---|
| `gen_ai.client.operation.duration` | seconds | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.operation.name` |
| `gen_ai.client.token.usage` (counter) | tokens | `gen_ai.system`, `gen_ai.request.model`, `direction=input|output` |
| `gen_ai.client.error.count` (counter) | 1 | `gen_ai.system`, `gen_ai.request.model`, `error.type` |

The reference workload's two custom histograms (`llm_inference_duration_seconds`, `llm_stream_duration_seconds`) are retained alongside the GenAI semconv standard histograms; they coexist via standard Prometheus scrape.

## Tool-call spans

The platform extends GenAI conventions with MCP-specific attributes on tool-call spans:

- `mcp.tool.id`, `mcp.tool.version`, `mcp.tool.duration_ms`, `mcp.tool.exit_code`.
- When the tool internally calls an LLM, the `gen_ai.*` attributes apply to that span as well.

## A2A spans

A2A traffic emits spans with both GenAI semconv attributes and A2A-specific attributes:

- `a2a.task.id`, `a2a.task.method`, `a2a.peer.agent`, `a2a.peer.iss`, `a2a.direction`.

## Sampling

Default Collector sampling:

- 100% of spans with `error=true`.
- 100% of spans with `a2a.direction=inbound` (audit-critical).
- 100% of spans with `hitl.event` present.
- 5% of routine spans (parent-based sampling so a sampled root keeps its full tree).

Per-workload overrides are configurable.

## Span event payload caps

To keep the Collector from being a DoS target:

- `gen_ai.content.prompt` event body capped at 32 KB; truncation marked.
- `gen_ai.content.completion` event body capped at 32 KB; truncation marked.
- Tool input and output payloads beyond 4 KB are referenced by content-hash and stored separately.

## See also

- ADR-0006: Observability via OTel + LGTM + Langfuse.
- `docs/layers/L7-observability-reliability/README.md` — the L7 surface where conventions are enforced.
- `shared/py-common/telemetry.py` — the shared instrumentation helper that emits compliant spans.

## References

- OpenTelemetry GenAI conventions blog (May 14, 2026): https://opentelemetry.io/blog/2026/genai-observability/
- Uptrace OTel for AI systems (April 2026): https://uptrace.dev/blog/opentelemetry-ai-systems
- Datadog native GenAI semconv (December 2025): https://www.datadoghq.com/blog/llm-otel-semantic-convention/
- PII redaction guidance (May 2026): https://maketocreate.com/opentelemetry-genai-tracing-ai-agents-without-leaking-pii/
