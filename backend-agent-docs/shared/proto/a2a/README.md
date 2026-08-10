# shared/proto/a2a/

A2A protocol schemas. Source for `a2a-adapter`'s inbound JSON-RPC handling and Agent Card generation.

```mermaid
flowchart LR
    A2A_SPEC[a2a/agent-card.schema.json<br/>a2a/task.schema.json] -->|validate inbound| A2A_SVC[L5 a2a-adapter]
    A2A_SPEC -->|generate| CARD[Agent Card<br/>/.well-known/agent.json]
    PEER[External A2A peer] -->|GET| CARD
    PEER -->|POST /a2a/tasks JSON-RPC 2.0| A2A_SVC
    A2A_SVC -->|validated envelope| ORCH[L3 agent-orchestrator]
```

## Files

- `agent-card.schema.json` — JSON Schema for the Agent Card document.
- `task.schema.json` — JSON Schema for the A2A Task object.
- `jsonrpc-envelope.schema.json` — JSON-RPC 2.0 envelope for A2A.

## References

- A2A specification site: https://a2a-protocol.org
- Protocol note: `docs/protocols/a2a.md`.
- Decision rationale: `docs/adr/0003-protocols-mcp-and-a2a.md`.
