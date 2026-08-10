# Testing Strategy

This document specifies the testing strategy for **every service component** in the platform. The harness engineering document covers application-level evaluation (does the agent produce correct outputs?). This document covers traditional software testing — does the service behave correctly, deterministically, and robustly under stress?

Both layers are required. A service that passes DeepEval suites but does not handle a NATS reconnect is not production-grade. A service that handles every failure mode but produces wrong agent outputs is not useful. The two test layers are complementary, not redundant.

## The test pyramid for an agent platform

```
                  ┌───────────────────────────────┐
                  │   E2E + chaos (staging only)  │  ← few, slow, full-stack
                  ├───────────────────────────────┤
                  │   Eval harness (CI gated)     │  ← see harness-engineering.md
                  ├───────────────────────────────┤
                  │   Contract tests              │  ← AsyncAPI / OpenAPI / A2A schemas
                  ├───────────────────────────────┤
                  │   Integration tests           │  ← service + real backend (Postgres etc)
                  ├───────────────────────────────┤
                  │   Unit tests                  │  ← most numerous, fastest
                  └───────────────────────────────┘
```

Every service has tests at every level. Pyramid shape is enforced (more units than integrations, more integrations than E2E).

## Per-service requirements

Every service under `services/*/` ships with a `tests/` directory containing:

```
tests/
  unit/                      # pytest, no I/O, mocks for everything external
  integration/               # pytest with testcontainers (real Postgres, real Redis, real NATS)
  contract/                  # schemathesis (HTTP) and AsyncAPI runner (NATS)
  load/                      # locust scripts for the steady-state load profile
  chaos/                     # toxiproxy scripts for failure injection (staging only)
```

CI enforces:

- ≥ 80% line coverage from unit tests (gate, not informational).
- 100% of public APIs have at least one contract test.
- Every NATS subject the service publishes or consumes has an AsyncAPI contract test.
- Load tests run nightly against staging.
- Chaos tests run weekly against staging.

## What gets tested per service category

### Agent runtime services (`agent-orchestrator`, `agent-worker`)

| Concern | Test category |
|---|---|
| LangGraph node logic | Unit (mocked LLM) |
| State-machine transitions | Unit |
| NATS publish/consume happy path | Integration (testcontainers NATS) |
| NATS reconnect after broker restart | Chaos |
| At-least-once delivery with idempotency | Integration |
| Worker subtask deadline enforcement | Unit + integration |
| HITL gate persistence across pod restart | Integration (testcontainers Postgres) |
| End-to-end run with all heuristics | DeepEval (see `harness-engineering.md`) |
| 100 concurrent runs sustained for 5 min | Load |
| Behavior when LLM provider returns 500s | Chaos (toxiproxy) |

### Memory services (`memory-svc`, `session-svc`)

| Concern | Test category |
|---|---|
| Each backend client (Graphiti, Qdrant, Redis, Postgres) | Unit (mocked clients) |
| Each backend with real instance | Integration (testcontainers FalkorDB, Qdrant, Redis, Postgres) |
| Hybrid search returns valid RRF-fused results | Integration |
| Reranker reduces top-50 → top-K deterministically | Unit |
| Per-workload partitioning (X-Workload-App enforced) | Contract |
| Compaction preserves key facts | DeepEval semantic check |
| Concurrent writes from many workers | Load |
| FalkorDB failover | Chaos |

### Tooling services (`mcp-registry`, `mcp-sandbox-runner`, `a2a-adapter`)

| Concern | Test category |
|---|---|
| Manifest schema validation | Unit |
| Allowlist enforcement | Unit + integration |
| Sandbox lifecycle (allocate, exec, reap) with mock CubeMaster | Unit |
| Sandbox lifecycle with real CubeSandbox | Integration |
| Idempotency cache hit/miss | Integration (testcontainers Redis) |
| Tool deadline enforcement | Integration |
| A2A Agent Card generation from CRD | Unit |
| A2A inbound task ingestion | Contract (JSON-RPC 2.0 schema) |
| HITL gate event emission | Integration |
| Sandbox cold start p99 | Load |
| Sandbox crash mid-execution | Chaos |

### Evaluation service (`eval-svc`)

| Concern | Test category |
|---|---|
| Each judge prompt scores synthetic inputs correctly | Unit |
| Langfuse client read + write | Integration |
| DeepEval suite invocation | Unit (mocked DeepEval) |
| Ragas evaluation on a fixed dataset | Integration |
| Score regression alerting threshold | Unit |

## Patterns common to every service

### Schema validation everywhere

Every HTTP response, every NATS message payload, every tool input and output is described by a Pydantic model. The model is the single source of truth; the OpenAPI / AsyncAPI / MCP manifest files are generated from the models (or validated against them in CI).

Schema violations are tested explicitly. Every service has a `test_schema_violations.py` that confirms invalid inputs are rejected with the expected error.

### Determinism via dependency injection

Every external dependency (LLM, vector store, graph store, NATS, Redis, Postgres, sandbox, audit sink) is accessed through a Protocol-typed client. Production wires the real client; tests inject a mock or a testcontainers-backed instance.

### Time mocking

Tests that depend on time (deadlines, TTLs, sliding windows) use `freezegun` or equivalent. No `time.sleep()` in tests except in the load and chaos suites.

### Goldens for stable outputs

Tests that compare structured outputs (e.g., LangGraph state at end of node) use golden files in `tests/__golden__/`. Updates require explicit `--update-goldens` flag and PR review.

## Contract testing

Inter-service edges are validated against schemas in `shared/proto/`. The CI flow:

1. Producer pushes a change to an AsyncAPI spec.
2. Consumer's contract test verifies it can decode every message valid under the new spec.
3. Producer's contract test verifies it only emits messages valid under the new spec.
4. If consumer is broken, producer's PR is blocked.

Tools:

- HTTP: `schemathesis` (property-based testing against OpenAPI).
- NATS: a custom AsyncAPI runner under `shared/py-common/contract/` (Stage 07).
- A2A: JSON-RPC 2.0 schema validation in `a2a-adapter` tests.
- MCP: manifest JSON Schema validation in `mcp-registry` tests.

## Integration testing with testcontainers

The `testcontainers-python` library provides ephemeral Postgres, Redis, NATS, FalkorDB, Qdrant for integration tests. Pattern:

- Per-test-class container spin-up via pytest fixtures.
- Container reused across tests in the same class for speed.
- Always real containers, never mocked — the point of an integration test is to catch what mocks miss.

CI runs integration tests on every PR but allows them to run in parallel (≤ 4-way) to bound wall-clock time.

## Load testing

`locust` scripts per service simulate the steady-state load profile:

| Service | Steady-state RPS |
|---|---|
| Kong | 100 |
| `agent-orchestrator` | 20 |
| `agent-worker` (per pod) | 50 (consumer ack budget) |
| `memory-svc` | 100 (mix of reads and writes) |
| `mcp-sandbox-runner` | 30 |

Load tests run nightly against staging. Latency regression alerts fire if p99 increases more than 20% week-over-week.

## Chaos testing

`toxiproxy` injects failures:

- Network latency on the path to LLM providers.
- Packet loss on NATS.
- Connection resets on Postgres.
- Full unavailability on individual backends (Qdrant, FalkorDB).
- CPU pressure on `agent-worker` pods.

The platform's stated commitments (circuit breaker, at-least-once delivery, graceful degradation) are validated empirically.

Chaos tests run weekly against staging. New chaos scenarios accompany every ADR that introduces a new failure mode.

## E2E testing

A small set of E2E suites live under `evals/e2e/` and run nightly against staging. Each E2E:

1. Provisions a fresh workload namespace via ArgoCD.
2. Sends representative traffic through Kong.
3. Asserts on:
   - End-to-end latency.
   - DeepEval-style application correctness.
   - Telemetry presence in Langfuse and Grafana.
   - Audit-trail presence in ClickHouse.

E2E failures gate the staging-to-production promotion in Stage 13.

## Mutation testing (informational)

Optional. `mutmut` runs nightly on `services/L3-agent-runtime/` to surface code that has tests but is not actually exercised by them. Findings are reviewed; not gated.

## Anti-patterns

- **Tests that hit live LLMs by default.** Already covered in `harness-engineering.md`.
- **Mocks all the way down.** A service with only unit tests does not exercise its real Postgres queries; integration tests catch the rest.
- **One giant E2E in place of a pyramid.** E2E is slow, flaky, and a bad debugging surface. Pyramid bottom up.
- **No chaos testing in staging.** Production failure modes are not theoretical; they are testable.
- **Coverage gates without contract tests.** Coverage can be gamed; contract violations are objective.

## Cross-references

- `harness-engineering.md` — application-level evaluation (the eval layer of the pyramid).
- `heuristic-engineering.md` — the heuristic catalog that DeepEval suites verify.
- Each service's own `tests/README.md` — service-specific test inventory (to be added in each implementation stage).

## References

- Sitepoint, "AI Agent Testing Automation: Developer Workflows for 2026": https://www.sitepoint.com/ai-agent-testing-automation-developer-workflows-for-2026/
- CloudQA, "2026 Software Testing Trends: The Shift from Scripted to Agentic AI" (contract testing reduces environment complexity by 80%): https://cloudqa.io/2026-software-testing-trends-the-shift-from-scripted-to-agentic-ai/
- vtestcorp, "Agentic Testing: The Complete Guide": https://vtestcorp.com/insights/agentic-testing-the-complete-guide-to-ai-powered-software-testing-in-2026/
- Industry references for testcontainers, locust, toxiproxy, schemathesis, freezegun, mutmut.
