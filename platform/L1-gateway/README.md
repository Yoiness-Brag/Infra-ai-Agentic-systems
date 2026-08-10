# L1 — Gateway

Kong AI Gateway installation and configuration. The only request perimeter on the platform.

```mermaid
flowchart LR
    EXT[External caller] -->|HTTPS + JWT| KONG[Kong AI Gateway<br/>L1]
    KONG -->|/chat/*| L3[L3 — agent-orchestrator]
    KONG -->|/a2a/*| L5[L5 — a2a-adapter]
    KONG -.->|OTLP| L7[L7 — Alloy]
    KONG -->|ai-proxy-advanced egress| LLM[LLM Providers]
```

## Contents

- `kong/` — Kong Helm chart values, Kong plugin configurations, AI plugin bundle settings.

## References

- Layer specification: `docs/layers/L1-interface-and-entry/README.md`.
- Decision rationale: `docs/adr/0012-gateway-kong-over-kgateway.md`.
- Kong AI Gateway product page: https://konghq.com/products/kong-ai-gateway
