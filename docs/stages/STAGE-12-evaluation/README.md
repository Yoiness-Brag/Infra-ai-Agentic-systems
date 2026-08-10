# Stage 12 — Evaluation Pipeline (four-tool harness composition)

## Goal

Land the platform's evaluation closure: port the five LLM-as-judge metric prompts from the reference workload into `eval-svc`, implement online scoring against live Langfuse traces, and stand up the **four-tool harness composition** that gates CI on every change to agent-runtime, memory, and tooling services.

The harness composition is non-negotiable: no single tool covers all four evaluation layers. Each tool owns a layer; together they form the platform's quality bar.

## Depends on

Stage 03 (observability backbone including Langfuse) and Stage 07 (orchestrator and worker producing traces to score). RAG-specific evaluation also depends on Stage 08 (memory-svc + rerank-svc).

## Deliverables

### Online: five LLM-as-judge metrics

- `services/L7-evaluation/eval-svc/` with the five judge prompts ported verbatim from the reference workload: `hallucination.md`, `helpfulness.md`, `relevancy.md`, `conciseness.md`, `toxicity.md`.
- `POST /eval/online/score` endpoint for synchronous scoring.
- Cron-triggered job that reads new Langfuse traces every 60 seconds, scores them via the five metrics, writes scores back to Langfuse trace metadata.
- Grafana panels showing score distributions; Langfuse score histograms.
- Score-regression alerting: 10% rolling p50 drop fires an alert via Mimir Ruler.

### Offline: four-tool CI harness composition

| Tool | Layer | Where | Threshold |
|---|---|---|---|
| **DeepEval** | Application unit (pytest-style) | `evals/deepeval-suites/` | 90% pass rate |
| **Promptfoo** | Prompt matrices + red-team | `evals/promptfoo/` | No >5% regression vs baseline; zero failures on must-pass red-team subset |
| **Ragas** | RAG-specific | `evals/ragas-suites/` | Faithfulness >0.90, Answer Relevancy >0.85, Context Precision >0.80, Context Recall >0.75 |
| **Inspect AI** | Safety + capability (UK AISI) | `evals/inspect-suites/` | Zero failures on must-pass; warnings tolerated on exploratory |

### Golden datasets

- `evals/datasets/agent-flow-basic.jsonl` — canonical agent runs.
- `evals/datasets/rag-faithfulness.jsonl` — RAG ground-truth Q/A pairs.
- `evals/datasets/tool-selection-edge-cases.jsonl` — ambiguous and adversarial tool-selection inputs.
- `evals/datasets/safety-probes.jsonl` — jailbreak and prompt-injection vectors.

### CI integration

- `.github/workflows/ci-evals.yaml` (Stage 13 wires the trigger) that runs all four tool suites on every PR touching `services/L3-agent-runtime/`, `services/L4-context-and-memory/`, `services/L5-tooling-integration/`, or `services/L7-evaluation/`.
- Per-suite reports posted to the PR as a status check.
- Threshold misses block the merge; ADR required to override.

### Heuristic regression suite

- `evals/deepeval-suites/test_heuristics.py` — verifies that every entry in the heuristic catalog (`docs/protocols/heuristic-engineering.md`) behaves as specified, using mocked LLM and tool layers.

## Non-goals

- No autonomous prompt-tuning; scoring is read-only and feedback-loop driven, not auto-corrective.
- No model-level benchmarks (HELM, lm-evaluation-harness, OpenCompass). Those are out of scope; we evaluate the *agent system*, not the underlying models.

## Acceptance criteria

1. The five online metrics produce non-trivial scores on synthetic and real production traces; histograms visible in Langfuse and Grafana.
2. DeepEval suites fail a deliberately broken PR (mutation-test sanity check).
3. Ragas suite asserts the four thresholds on the rag-faithfulness golden dataset.
4. Promptfoo red-team suite catches at least one known prompt-injection vector.
5. Inspect AI safety suite gates on the must-pass jailbreak subset.
6. The heuristics regression suite passes against the documented catalog.
7. A merged PR that touches `services/L3-agent-runtime/` runs all four suites and reports per-suite status.

## Operational note

Setup budget: 2-3 weeks of focused engineering effort (per Intuz's 100-deployment study). Worth budgeting on the calendar before the stage starts.

## Next stage

Stage 13 (CI/CD GitOps) — wires the harness invocations as CI gates and the score-regression alerts as deployment guardrails.

## See also

- `docs/protocols/harness-engineering.md` — the doctrine this stage implements.
- `docs/protocols/heuristic-engineering.md` — the catalog the heuristics regression suite asserts on.
- `docs/protocols/rag-architecture.md` — the RAGAS thresholds and their interpretation.
- `docs/reference/upstream-repo-mapping.md` — origin of the five judge prompts.
