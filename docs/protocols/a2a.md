# A2A — Agent-to-Agent Protocol

This document is the platform-specific implementation note for A2A. The protocol specification itself is at the Linux Foundation; this document covers how the platform consumes and exposes A2A.

## Status of A2A

A2A is an open standard hosted by the Linux Foundation since June 23, 2025. By April 2026, more than 150 organizations contribute or use it in production; SDKs are available in Python, JavaScript, Java, Go, and .NET; Google ADK 1.0 shipped GA in April 2026 as the cross-language reference SDK. IBM ACP and BeeAI were officially merged under A2A; Cisco AGNTCY is also part of the same Linux Foundation Agentic AI Foundation. The platform supports A2A and does not implement separate code paths for ACP or AGNTCY.

## Role in the platform

A2A is the contract between agents that do not share a runtime. Two kinds of A2A traffic exist:

1. **Inbound**: a peer agent outside the platform invokes a workload inside the platform.
2. **Outbound**: a workload inside the platform delegates to a peer agent outside.

Both flow through the `a2a-adapter` service in L5 so that governance, telemetry, retry, and credential handling are uniform.

## Agent Card

Every workload that opts in to A2A exposes an Agent Card at `/.well-known/agent.json`. The card is generated from kagent Agent CRD fields by the `a2a-adapter`. Minimum fields per the A2A spec:

```json
{
  "name": "string",
  "description": "string",
  "url": "https://gw.platform.local/a2a/{workload}/",
  "version": "string",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "string",
      "name": "string",
      "description": "string",
      "inputModes": ["text"],
      "outputModes": ["text"]
    }
  ],
  "authentication": {
    "schemes": ["Bearer"]
  }
}
```

The kagent Agent CRD has a `spec.a2aSkills` field that lists the skills to expose. `a2a-adapter` reads this on reconciliation and updates the card.

## Task lifecycle

A2A task semantics:

1. A peer sends `tasks/send` (or `tasks/sendSubscribe` for streaming) via JSON-RPC 2.0 to the workload's URL.
2. `a2a-adapter` validates the peer's JWT, applies workload-specific rate limits, and translates the task into the internal `SubtaskRequest` envelope.
3. The internal flow is identical to an L1-originated request from that point on. The orchestrator dispatches, workers execute, results flow back.
4. The reverse translation happens on the response: the internal result becomes an A2A `tasks/result` (or streaming events).
5. Audit and OTel telemetry record the peer identity and the A2A task id throughout.

## Outbound delegation

L3 services use an internal A2A client that sends requests through `a2a-adapter`. The adapter:

- Resolves the peer's Agent Card.
- Selects the appropriate skill based on the calling agent's intent.
- Signs the request with the workload's outbound credentials.
- Applies retry-with-jitter and circuit-breaker policy.
- Records OTel spans on the calling side with peer identity attributes.

## Compatibility with ACP, BeeAI, AGNTCY

ACP and BeeAI are now part of A2A at the Linux Foundation; AGNTCY shares the same umbrella. The platform interoperates with ACP-compatible and BeeAI-compatible agents via A2A semantics. No separate code path is implemented.

## Telemetry conventions

A2A spans emit:

- `a2a.task.id`
- `a2a.task.method` (`tasks/send`, `tasks/sendSubscribe`, `tasks/cancel`, etc.)
- `a2a.peer.agent` (Agent Card name)
- `a2a.peer.iss` (JWT issuer)
- `a2a.direction` (`inbound` | `outbound`)

Plus the standard OTel attributes and any GenAI semconv attributes that apply to the call.

## See also

- ADR-0003: MCP and A2A as the platform's two protocol standards.
- `docs/layers/L3-agent-runtime/README.md` — workload exposure.
- `docs/layers/L5-tooling-and-integration/README.md` — the adapter implementation.
- `shared/proto/a2a/` — Agent Card schema and JSON-RPC method definitions.

## References

- A2A protocol homepage: https://a2a-protocol.org
- Linux Foundation launch press release: https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents
- A2A 150+ organizations milestone (April 2026): https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
- ACP / BeeAI consolidation under A2A: https://a2ac.io/projects/acp-beeai
