# Heuristic Engineering

This document specifies the **codified decision rules** that the platform's `agent-orchestrator` and `agent-worker` services apply on every reasoning step. Heuristic engineering is the discipline of taking decisions the agent would otherwise make implicitly (via LLM reasoning) and lifting the ones that matter for cost, latency, safety, or reliability into explicit, testable, observable rules.

Heuristics are not a replacement for LLM reasoning. They are guardrails *around* it. The LLM decides what tool to call; the heuristic decides whether the call is allowed given the budget. The LLM decides what to say; the heuristic decides whether to summarize the conversation first. The orchestrator hosts the heuristics; the worker honors them.

## Why heuristics, not pure LLM reasoning

An agent that decides everything via LLM calls is expensive, slow, and non-deterministic. Production agents fail when they:

- Loop on the same tool call.
- Burn token budget on a query that a small classifier could route.
- Skip context compaction and overflow the window mid-conversation.
- Escalate to the lead model for trivial questions.
- Continue past their deadline.

Each of those failures has a cheap, deterministic mitigation. The platform's heuristic layer is where those mitigations live.

## Heuristic catalog

The catalog is organized by the decision the heuristic informs. Each heuristic has a name, a trigger condition, an action, a cost (cheap = O(1), medium = small classifier call, expensive = small-model LLM call), and an observability hook.

### Dispatch heuristics (orchestrator decides whether to fan out)

| Heuristic | Trigger | Action | Cost | Metric |
|---|---|---|---|---|
| `single-step-bypass` | Estimated subtask count ≤ 1 | Skip dispatch; run inline in the orchestrator. | O(1) | `orchestrator.dispatch.bypass.count` |
| `parallel-fan-out` | Estimated subtask count ≥ 2 *and* subtasks declared independent in the plan | Publish all subtasks on `agents.subtask.<sid>` in parallel. | O(1) | `orchestrator.dispatch.parallel.count` |
| `sequential-chain` | Subtasks declared dependent (B requires A's result) | Publish A, await ack, publish B. | O(1) | `orchestrator.dispatch.sequential.count` |
| `max-fan-out-cap` | Estimated subtask count > `Agent.spec.maxSubtasks` (default 8) | Reject the plan; ask the LLM to re-plan with a smaller fan-out. | O(1) | `orchestrator.dispatch.cap_hit.count` |

### Model-selection heuristics (which LLM serves which call)

The platform routes through Kong `ai-proxy-advanced`, but the routing *decision* originates in the agent. Heuristics make that decision cheap.

| Heuristic | Trigger | Action | Cost | Metric |
|---|---|---|---|---|
| `lead-model-required` | Step is the orchestrator's plan or final reconciliation | Force the lead model (e.g., `claude-sonnet-4-5`). | O(1) | `model.route.lead.count` |
| `worker-default-model` | Step is a subtask | Use the worker default (e.g., `claude-haiku-4-5`); 5-10x cheaper. | O(1) | `model.route.worker.count` |
| `local-model-fallback` | Worker default is unavailable *and* the step is low-stakes (no tool calls, no PII risk) | Fall through to local Ollama. | O(1) | `model.route.fallback.count` |
| `confidence-escalation` | Worker output's self-reported confidence < threshold (0.6 default) | Re-run on the lead model. | Cheap; output already classified. | `model.route.escalation.count` |

### Memory and compaction heuristics

| Heuristic | Trigger | Action | Cost | Metric |
|---|---|---|---|---|
| `compaction-token-cap` | Conversation token count exceeds `compactionThreshold` (default 8K) | Synchronously call `session-svc` to compact before the next turn. | Medium (small-model summary). | `memory.compaction.triggered.count` |
| `compaction-turn-cap` | Conversation turn count exceeds `compactionTurns` (default 24) | Same as above. | Medium. | `memory.compaction.triggered.count` |
| `episode-promotion` | Worker generated a fact tagged `durable=true` | Write as an episode to Graphiti via `memory-svc`. | Cheap (async via `memory.ingest.*` on NATS). | `memory.episode.promoted.count` |
| `episode-invalidation` | Worker generated a fact that contradicts a Graphiti episode (entity + property match) | Set `valid_to=now()` on the old episode; insert the new one. | Cheap (single Graphiti write). | `memory.episode.invalidated.count` |

### Retrieval heuristics

| Heuristic | Trigger | Action | Cost | Metric |
|---|---|---|---|---|
| `hybrid-first` | Worker needs external knowledge | Call `memory-svc` with `mode=hybrid` (RRF over dense + sparse); see `rag-architecture.md`. | O(1) on retrieval; rerank adds ms. | `retrieval.hybrid.count` |
| `graph-for-relations` | Query contains entity-relation language ("who manages X", "what depends on Y") | Use Graphiti graph query first; fall back to hybrid if empty. | O(1) decision; query cost varies. | `retrieval.graph.count` |
| `low-recall-fallback` | Hybrid returned top-1 score below threshold (0.3 default) | Run a second hybrid pass with query rewriting via small LLM. | Medium. | `retrieval.fallback.count` |
| `chunk-deduplication` | Multiple chunks from the same source document in the top-K | Keep only the highest-ranked; lift K to fill the gap. | O(K). | `retrieval.dedup.count` |

### Tool-use heuristics

| Heuristic | Trigger | Action | Cost | Metric |
|---|---|---|---|---|
| `tool-allowlist-check` | Worker requested a tool | `mcp-sandbox-runner` verifies against `Agent.spec.toolAllowlist`. Reject if not on list. | O(1). | `tool.denied.count` |
| `tool-loop-detect` | Same tool called with same input within the same run, twice | Reject the second call; return the cached result of the first. | O(1) via idempotency key in Redis. | `tool.loop_detected.count` |
| `hitl-gate` | Tool manifest has `requires_approval: true` | Emit `audit.hitl.<workload>` event; pause; resume on approval. | Bounded by human. | `tool.hitl.pending.count` |
| `tool-deadline` | Tool call exceeds `tool.timeout_ms` from manifest | Kill sandbox; mark failure; orchestrator decides retry vs abort. | O(1). | `tool.deadline_hit.count` |

### Termination heuristics

| Heuristic | Trigger | Action | Cost | Metric |
|---|---|---|---|---|
| `run-deadline` | Run elapsed time > `Agent.spec.runDeadline` (default 90s) | Stop; return best-effort partial response. | O(1). | `run.deadline_hit.count` |
| `step-budget` | Reasoning steps > `Agent.spec.maxSteps` (default 12) | Stop; return current answer. | O(1). | `run.step_budget_hit.count` |
| `token-budget` | Cumulative tokens > `Agent.spec.tokenBudget` (default 50K) | Stop; return current answer. | O(1). | `run.token_budget_hit.count` |
| `cost-budget` | Estimated USD cost > `Agent.spec.costBudgetUsd` (default 0.50) | Stop. | O(1) (Kong's per-call cost meter). | `run.cost_budget_hit.count` |

## Where each heuristic lives in the code

- **Orchestrator (`services/L3-agent-runtime/agent-orchestrator/`)** owns dispatch, model-selection, run-level termination, episode promotion/invalidation.
- **Worker (`services/L3-agent-runtime/agent-worker/`)** owns retrieval, tool-use heuristics on the producer side.
- **`mcp-sandbox-runner`** enforces `tool-allowlist-check`, `tool-loop-detect`, `hitl-gate`, `tool-deadline` on the receiver side.
- **`memory-svc` / `session-svc`** owns `compaction-token-cap`, `compaction-turn-cap`.
- **Kong** owns `cost-budget` via `ai-rate-limiting-advanced` token accounting.

Defense in depth: model-selection lives in two places (worker emits a hint, Kong's `ai-proxy-advanced` makes the final routing decision); allowlist lives in two places (`Agent.spec.toolAllowlist` is the source of truth, but `mcp-sandbox-runner` re-checks).

## Observability

Every heuristic increments a counter in the `heuristic.<name>` metric family. Dashboards under `platform/L7-observability/grafana-dashboards/heuristics.json` (Stage 12) show:

- Top heuristics by hit rate (sanity check: are they ever firing?).
- Heuristics that never fire (dead code candidates).
- Heuristics that fire >50% of runs (potential design smell — maybe the default budget is too tight).

Eval gates: a regression suite under `evals/deepeval-suites/heuristics.py` (Stage 12) asserts that the catalog above behaves as specified, using mocked LLM and tool layers.

## Adding a new heuristic

The checklist:

1. Name it. Convention: `<scope>-<verb>`.
2. Specify the trigger as a boolean expression over observable state.
3. Specify the action as a deterministic function call.
4. Estimate the cost.
5. Define the metric and add it to the heuristics dashboard.
6. Write a DeepEval test under `evals/deepeval-suites/heuristics.py`.
7. Update this catalog.

If the heuristic affects a public contract (e.g., a default budget number), write an ADR.

## Anti-patterns

- **Heuristics inside the LLM prompt** ("only call tools twice"). The LLM will violate them; encode them as deterministic checks.
- **Heuristics without metrics**. If a heuristic does not emit a counter, we cannot see when it fires or whether it has gone dormant.
- **Heuristics that contradict each other silently**. We sequence them explicitly in the orchestrator code; if two heuristics could fire on the same event, the catalog above documents the order.

## Cross-references

- `context-engineering.md` — the four dimensions (Selection, Retrieval, Compression, Persistence) that several heuristics implement.
- `rag-architecture.md` — the retrieval implementation behind `hybrid-first` and `graph-for-relations`.
- `harness-engineering.md` — how the heuristic catalog is tested in CI.
- `docs/layers/L2-orchestration-control-plane/README.md` — dispatch heuristics in operational context.
- `docs/layers/L3-agent-runtime/README.md` — model-selection and termination heuristics in agent context.

## References

- Anthropic Research, "Building effective agents" — orchestrator-worker pattern and explicit-decision heuristics.
- Intuz / Towards Data Science, "Building an Evaluation Harness for Production AI Agents: A 12-Metric Framework From 100+ Deployments" (2026): https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/
- Google ADK team's three-way-pressure framing (cost+latency / signal-degradation / overflow) informs the budget-based termination heuristics.
