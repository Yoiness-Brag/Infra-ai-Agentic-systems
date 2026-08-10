# ADR-0003: Adopt MCP and A2A as the platform's two protocol standards

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

Agentic systems in 2026 have converged on two open protocols, both governed by the Linux Foundation:

- **MCP (Model Context Protocol)**: standardizes how an agent connects to tools and data sources. Donated by Anthropic, now under the Linux Foundation Agentic AI Foundation.
- **A2A (Agent-to-Agent)**: standardizes how agents discover and communicate with each other across frameworks and vendors. Donated by Google, hosted by the Linux Foundation since June 2025, with 150+ organizations in production by April 2026, SDKs in Python, JavaScript, Java, Go, .NET.

Other protocols exist but are no longer separate concerns:

- **IBM ACP (Agent Communication Protocol)** and **BeeAI**: officially merged under A2A at the Linux Foundation. ACP-compatible agents are reachable via A2A semantics.
- **Cisco AGNTCY**: also under the Linux Foundation Agentic AI Foundation umbrella. Converged with A2A.

A naive implementation might support all three plus a bespoke fourth. That doubles or triples the integration surface and the test matrix.

## Decision

The platform supports exactly two protocols:

1. **MCP** for the tool plane. Every tool the platform exposes (via `mcp-registry`) carries an MCP manifest. Kong AI Gateway's MCP plugin handles MCP traffic at the perimeter when appropriate.
2. **A2A** for inter-agent communication. The `a2a-adapter` service exposes every platform workload as an A2A endpoint with an Agent Card at `/.well-known/agent.json` and JSON-RPC 2.0 task endpoints.

ACP-compatible and AGNTCY-compatible peers are reachable via A2A by virtue of the Linux Foundation consolidation. We do not implement separate code paths for ACP or AGNTCY.

## Consequences

Positive:

- One integration surface for the tool plane, one for the inter-agent plane.
- We track two upstream specs, not five.
- Compatibility with the consolidated Linux Foundation ecosystem.

Negative:

- If a future protocol diverges from A2A (e.g., a new standard for streaming binary multi-modal), we will need to revisit.
- We do not optimize for any vendor-specific dialect.

Neutral:

- Both protocols are open, multi-vendor, and have active SDK ecosystems.

## Alternatives considered

- **Implement MCP + A2A + ACP + AGNTCY natively**: rejected because ACP and AGNTCY are subsumed under A2A at the Linux Foundation. Maintaining four code paths would be pure overhead.
- **Implement only MCP and skip A2A**: rejected because cross-vendor agent delegation is an explicit Excalidraw and requirement-list item.
- **Implement a bespoke protocol**: rejected because the cost of building and maintaining a new protocol exceeds any benefit, and isolates us from the 150+ A2A adopters.

## References

- A2A protocol homepage: https://a2a-protocol.org
- Linux Foundation A2A press release: https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents
- A2A one-year adoption stats: https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
- ACP / BeeAI under A2A: https://a2ac.io/projects/acp-beeai
- MCP Kong integration: https://developer.konghq.com/ai-gateway/
