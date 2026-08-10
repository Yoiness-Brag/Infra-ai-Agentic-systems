# Harness Engineering

This document specifies the platform's evaluation harness — the quality layer around the agent runtime. A harness is the infrastructure that measures whether an agent produces correct outputs, catches regressions between releases, and gates deployments in CI. The teams shipping reliable AI agents in 2026 do not have better models; they have better evaluation infrastructure.

The platform adopts a **four-tool composition** rather than a single tool because no single tool covers all four evaluation layers. Each tool owns a layer and integrates with the others via shared datasets and shared score reporting (Langfuse + Grafana).

## The four-tool composition

| Tool | Layer | What it owns | Format |
|---|---|---|---|
| **DeepEval** | Application unit tests in CI | pytest-style assertions on agent behavior — tool selection, faithfulness, answer correctness, multi-step coherence | Python tests |
| **Promptfoo** | Prompt and model selection | Prompt matrices, A/B comparisons across models, red-team adversarial checks | YAML configs |
| **Ragas** | RAG quality | Faithfulness, Answer Relevancy, Context Precision, Context Recall on retrieval pipelines | Python |
| **Inspect AI** | Safety and capability evaluations | UK AI Security Institute composable framework; safety probes, jailbreak resistance, capability ceilings | Python |

Plus the five LLM-as-judge metrics ported from the reference workload (hallucination, helpfulness, relevancy, conciseness, toxicity), which run as **online scoring** against live Langfuse traces via `eval-svc`.

This is not "use four tools." It is "each tool answers a different question." If we only had DeepEval, we would lack the prompt-matrix discipline that Promptfoo provides. If we only had Promptfoo, we would lack the pytest-native integration that DeepEval gives. Ragas covers a domain neither owns. Inspect AI covers safety probes neither does.

## Where each lives in the repo

```
services/L7-evaluation/eval-svc/
  src/
    evaluator.py             # The five LLM-as-judge online metrics
    helpers.py
    main.py                  # Reads Langfuse traces, writes scores back
    schemas.py
  prompts/
    hallucination.md         # ported from reference workload
    helpfulness.md
    relevancy.md
    conciseness.md
    toxicity.md

evals/
  datasets/                  # Golden datasets, JSONL
    agent-flow-basic.jsonl
    rag-faithfulness.jsonl
    tool-selection-edge-cases.jsonl
    safety-probes.jsonl
  deepeval-suites/           # DeepEval pytest suites
    test_agent_orchestrator.py
    test_agent_worker.py
    test_memory_svc.py
    test_heuristics.py       # tests the heuristic catalog from heuristic-engineering.md
  promptfoo/                 # Promptfoo YAML configs
    prompt-matrix.yaml
    model-selection.yaml
    red-team.yaml
  ragas-suites/              # Ragas Python suites
    rag_quality.py
  inspect-suites/            # Inspect AI suites
    safety_probes.py
    jailbreak_resistance.py
    capability_ceiling.py
```

## How the four-tool composition runs

### In CI (offline, blocking)

On every PR that touches `services/L3-agent-runtime/`, `services/L4-context-and-memory/`, `services/L5-tooling-integration/`, or `services/L7-evaluation/`:

1. **Unit tests** — every service's own `tests/` directory runs first.
2. **DeepEval suites** — application-level agent tests run with mocked LLMs (deterministic) and a small live-LLM subset for non-determinism sanity. Threshold: 90% pass rate.
3. **Ragas suite** — RAG quality on golden datasets. Threshold: Faithfulness > 0.90, Answer Relevancy > 0.85, Context Precision > 0.80, Context Recall > 0.75 (per ADR-0006 and `rag-architecture.md`).
4. **Inspect AI safety suite** — jailbreak resistance, prompt-injection probes, capability-ceiling assertions. Threshold: zero failures on the must-pass subset; warnings tolerated on the exploratory subset.
5. **Promptfoo matrix** — A/B against a baseline prompt-and-model combination. Threshold: no regression of more than 5% on the aggregate score.

Any threshold miss blocks the PR. Overrides require an ADR (it is an irreversible decision to weaken a quality gate).

### In production (online, observational)

`eval-svc` runs continuously:

- Reads new Langfuse traces every 60 seconds.
- Scores each via the five LLM-as-judge metrics.
- Writes scores back to Langfuse trace metadata.
- Aggregates to Grafana dashboards via Langfuse → Mimir bridge (Stage 12).

A score regression alert fires when any metric's 1-hour rolling p50 drops more than 10% from the 24-hour baseline.

## Mocking the LLM layer

DeepEval suites depend on deterministic behavior. The pattern:

- Every service defines an `LLMClient` protocol (Python `typing.Protocol`).
- The default implementation calls Kong's `ai-proxy-advanced` endpoint.
- Tests inject a `MockLLMClient` via dependency injection (FastAPI's `Depends`, or pytest fixture).
- The mock returns canned responses keyed by prompt hash.

A small subset of tests run *without* the mock against a live small model (e.g., local Ollama) to catch determinism drift. These tests are marked `@pytest.mark.live` and skipped by default in local dev.

## Schema validation

Every agent output is validated against a Pydantic model before it is considered a result. Schema-validation failures count as test failures even when the LLM "thought" it succeeded. This is enforced platform-wide via the shared `shared/py-common/middleware.py`.

## Multi-agent testing

The orchestrator-worker pattern produces inter-agent message flows that single-agent tests do not cover. The platform's pattern:

- Fixture-based eval that records a "tape" of NATS messages for a representative run.
- Replay-based tests that inject the tape into a test orchestrator with mock workers and verify the orchestrator's reconciliation.
- A second variant that replays into mock orchestrator with real workers (with mocked LLMs) to verify worker behavior under realistic message flows.

These live in `evals/deepeval-suites/test_multi_agent_flows.py` (Stage 12).

## Red-teaming

Promptfoo's built-in attack suite (500+ attack vectors as of 2026) runs nightly against `agent-orchestrator` in staging. Findings are tracked in GitHub issues, not auto-fixed. The Inspect AI `jailbreak_resistance.py` suite covers the must-pass subset that gates PRs.

## Contract testing

Inter-service edges (`agent-orchestrator` → NATS, NATS → `agent-worker`, anything → `memory-svc`, anything → `mcp-sandbox-runner`) are validated via contract tests against the AsyncAPI / OpenAPI schemas in `shared/proto/`. CI fails if a producer emits something a consumer's schema cannot accept.

We use `schemathesis` for HTTP and a custom AsyncAPI runner for NATS.

## Anti-patterns

- **One tool for everything.** Each tool above answers a question the others do not. Trying to do RAGAS metrics in DeepEval produces shallow approximations; trying to do prompt matrices in Ragas does not work.
- **Tests that hit live LLMs by default.** Non-determinism poisons the CI signal. Mock by default; live-LLM tests are explicit, marked, and rare.
- **Evals without thresholds.** A test with no pass/fail gate is documentation, not a test. Every eval has a threshold; every threshold appears in this document or in `evals/<suite>/README.md`.
- **Production scoring without baselines.** A metric without a baseline cannot detect regression. We compute baselines from 7-day rolling windows.

## Operational note

Setting up the full four-tool harness takes 2-3 weeks of focused engineering effort (per Intuz's 100-deployment study), assuming an LLM-judge evaluator is already configured. Stage 12 of the implementation roadmap budgets for this.

## Cross-references

- `heuristic-engineering.md` — the heuristic catalog tested by DeepEval.
- `rag-architecture.md` — the retrieval implementation evaluated by Ragas.
- `testing-strategy.md` — per-component testing strategy that complements this document.
- `docs/layers/L7-observability-reliability/README.md` — where eval-svc and the score backends live.

## References

- Pinggy, "AI Harness Engineering: The Layer That Makes Your LLM Applications Actually Work" (May 2026): https://pinggy.io/blog/best_ai_harnesses_to_supercharge_llm_models/
- Towards Data Science / Intuz, "Building an Evaluation Harness for Production AI Agents: A 12-Metric Framework From 100+ Deployments" (May 2026): https://towardsdatascience.com/building-an-evaluation-harness-for-production-ai-agents-a-12-metric-framework-from-100-deployments/
- Inference.net, "LLM Evaluation Tools: The Complete Comparison Guide (2026)": https://inference.net/content/llm-evaluation-tools-comparison/
- DevopsSchool, "Top 10 LLM Evaluation Harnesses": https://www.devopsschool.com/blog/top-10-llm-evaluation-harnesses-features-pros-cons-comparison/
- Best AI Web, "How to Benchmark LLMs with lm-evaluation-harness, HELM, and OpenCompass in 2026": https://www.bestaiweb.ai/how-to-benchmark-llms-with-lm-evaluation-harness-helm-and-opencompass-in-2026/
- Stanford CRFM HELM and UK AISI Inspect AI source projects.
- DeepEval (Confident AI), Promptfoo, Ragas, Inspect AI documentation.
