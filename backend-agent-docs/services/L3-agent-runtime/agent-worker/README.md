# agent-worker

The platform's subagent reference implementation. NATS consumer, KEDA-autoscaled, LangGraph state machine.

## Responsibilities

- Consume `agents.subtask.<session_id>` with bounded `MaxAckPending` (default 50 per pod).
- Read context handles (Graphiti episode IDs, Qdrant chunk IDs) — do not load full text until the LangGraph node needs it.
- Execute the subtask: LLM calls via Kong `ai-proxy-advanced`, retrievals via `memory-svc /retrieve`, tool calls via `mcp-sandbox-runner /tools/invoke`.
- Apply per-step heuristics: `worker-default-model`, `local-model-fallback`, `confidence-escalation`, `tool-loop-detect`.
- Publish results on `agents.result.<session_id>`.
- Ack on success; nack with redelivery on transient failure; deadline-kill on `tool-deadline` or `subtask-deadline`.

## One worker implementation

One worker, scaled horizontally. We do not maintain a "heavy" and "light" worker variant.

## Install and setup

Same pattern as agent-orchestrator. KEDA `ScaledObject` from `k8s/scaledobject.yaml` defines the autoscaling rule against NATS consumer lag.

```bash
# Local dev (consumes from local NATS)
uv sync
uv run python -m src.main

# In-cluster
helm upgrade --install agent-worker ./k8s/helm \
  --namespace workload-<app>-<env> \
  --values k8s/helm/values.yaml
```

## Flow

```mermaid
flowchart LR
    NATS[NATS agents.subtask.{sid}] -->|deliver| WRK[agent-worker pod]
    WRK -->|read context handle| MS[memory-svc]
    WRK -->|LLM call| KONG[Kong ai-proxy-advanced]
    WRK -->|tool call| MSR[mcp-sandbox-runner]
    MSR -->|exec| CUBE[(CubeSandbox)]
    WRK -->|write episode| MS
    WRK -->|publish agents.result| NATS_OUT[NATS agents.result.{sid}]
    KEDA[KEDA scaler] -.->|consumer lag| SCALE[Scale replicas]
    WRK -.->|OTLP| ALLOY[Grafana Alloy]
```

## References

- Same as agent-orchestrator.
- KEDA ScaledObject: https://keda.sh/docs/concepts/scaling-deployments/
- Layer specification: `docs/layers/L3-agent-runtime/README.md`

## Status

Service code lands at Stage 07.
