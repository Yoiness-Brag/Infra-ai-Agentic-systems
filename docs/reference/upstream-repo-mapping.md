# Upstream Reference Repository Mapping

This document records exactly which files from the [Fareed Khan production-grade-agentic-system](https://github.com/FareedKhan-dev/production-grade-agentic-system) repository we lift into this platform, where each file lands, and what is rewritten or discarded.

The reference repository is a FastAPI + LangGraph monolith with Langfuse, structlog, Prometheus, five LLM-as-judge prompts, and a Grafana llm_latency dashboard. It is single-process; we are multi-service. So the lift is selective: shared utilities and prompts move verbatim; service code is rewritten as multi-service components.

## Lift verbatim (with light path/import adjustments)

| Source path (in reference repo) | Destination (in this repo) | Why we lift it |
|---|---|---|
| `src/system/logs.py` | `shared/py-common/logging.py` | The structlog setup is mature and OTel-trace-id-aware. Every service uses it. |
| `src/system/middleware.py` | `shared/py-common/middleware.py` | Request-id, OTel context propagation, error mapping. |
| `src/system/telemetry.py` | `shared/py-common/telemetry.py` | OTel tracer/meter initialisation; aligned with our GenAI semconv standard. |
| `src/utils/sanitization.py` | `shared/py-common/sanitization.py` | Prompt sanitization helpers reusable across agent code and Kong's request-transformer config. |
| `src/agent/workflow.py` | `services/L3-agent-runtime/agent-orchestrator/src/workflow.py` | The LangGraph state machine is the orchestrator's reasoning loop. Adapted to publish subtasks via NATS instead of running synchronously. |
| `src/agent/state.py` | `services/L3-agent-runtime/agent-orchestrator/src/state.py` | State model for the LangGraph run. |
| `src/agent/nodes.py` | `services/L3-agent-runtime/agent-orchestrator/src/nodes.py` | Individual LangGraph nodes; some move to the worker. |
| `evals/prompts/hallucination.md` | `services/L7-evaluation/eval-svc/prompts/hallucination.md` | LLM-as-judge metric prompt. |
| `evals/prompts/helpfulness.md` | `services/L7-evaluation/eval-svc/prompts/helpfulness.md` | LLM-as-judge metric prompt. |
| `evals/prompts/relevancy.md` | `services/L7-evaluation/eval-svc/prompts/relevancy.md` | LLM-as-judge metric prompt. |
| `evals/prompts/conciseness.md` | `services/L7-evaluation/eval-svc/prompts/conciseness.md` | LLM-as-judge metric prompt. |
| `evals/prompts/toxicity.md` | `services/L7-evaluation/eval-svc/prompts/toxicity.md` | LLM-as-judge metric prompt. |
| `evals/evaluator.py` | `services/L7-evaluation/eval-svc/src/evaluator.py` | Score-computation logic. |
| `evals/helpers.py` | `services/L7-evaluation/eval-svc/src/helpers.py` | Eval support utilities. |
| `evals/main.py` | `services/L7-evaluation/eval-svc/src/main.py` | Eval entry point; adapted to read from Langfuse. |
| `evals/schemas.py` | `services/L7-evaluation/eval-svc/src/schemas.py` | Pydantic models for eval payloads. |
| `grafana/dashboards/json/llm_latency.json` | `platform/L7-observability/grafana-dashboards/llm_latency.json` | Reference workload's latency dashboard. Loaded into Grafana via sidecar. |

## Rewrite

| Source | Why rewritten | Destination |
|---|---|---|
| `Dockerfile` | Single-image monolith; we need per-service images. | Per-service `Dockerfile`s in each `services/*/` folder. |
| `docker-compose.yml` | Local-only orchestration; replaced by k3d + ArgoCD. | Not ported. The local dev path is `make local-up`. |
| `schema.sql` | SQLite-shaped DDL; we use Postgres with proper RLS, plus per-store backends (FalkorDB, Qdrant, Redis). | `platform/L4-data-plane/postgres/init/` for Postgres; FalkorDB and Qdrant are schema-less or schema-managed by Graphiti/Qdrant clients. |
| `src/api/main.py` | Single-process FastAPI app; we split into orchestrator and worker. | `services/L3-agent-runtime/agent-orchestrator/src/main.py` and `services/L3-agent-runtime/agent-worker/src/main.py`. |
| `src/api/routes.py` | Same. | Split per service. |
| `requirements.txt` | We use per-service `pyproject.toml` with `uv` lockfiles to keep dependency surfaces minimal per service. | `services/*/pyproject.toml`. |
| `prometheus.yml` config | Replaced by kube-prometheus-stack ServiceMonitors. | `platform/L7-observability/kube-prometheus-stack/values.yaml`. |
| `langfuse_init.py` | Langfuse is self-hosted at the platform level; clients use OTel-mediated integration. | Service code uses `shared/py-common/telemetry.py` rather than a Langfuse-specific init. |

## Discard

| Source | Why discarded |
|---|---|
| `tests/` (the empty test scaffolding) | The reference repo has pytest+httpx configured but zero actual test files. We write tests from scratch per service in `services/*/tests/`. |
| `notebooks/` | Exploration material; not platform code. |
| Any `.env.example` files | Replaced by per-service `.env.example` plus a Helm values pattern for K8s. |

## Adapt (not pure lift, but informed by the reference)

| Source pattern | What we adapt |
|---|---|
| `src/agent/workflow.py` graph topology | The reference is a single-process state machine. The platform version dispatches certain nodes as NATS subtasks consumed by `agent-worker`. The graph topology and node names carry over; the transport changes. |
| Reference workload's Prometheus histograms (`llm_inference_duration_seconds`, `llm_stream_duration_seconds`) | Kept alongside the OTel GenAI semconv histograms. Scraped by the kube-prometheus-stack and remote-written to Mimir. |
| Reference workload's structlog JSON line format | Adopted as the platform-wide log format. |
| Reference workload's mem0 integration | Mem0 is REMOVED entirely per ADR-0004 (one-stack-per-use-case rule). The mem0ai import is replaced with calls to `memory-svc /episodes` and `memory-svc /retrieve` during the Stage 07 port. |

## How the lift is staged

The actual port happens at:

- **Stage 07** (Agent runtime): orchestrator and worker code, `shared/py-common/*`.
- **Stage 12** (Evaluation): eval-svc and the five judge prompts.
- **Stage 03** (Observability): the Grafana dashboard.

At Stage 00 (this stage) we only document the mapping; no code is moved.

## See also

- ADR-0001: Monorepo layout.
- ADR-0011: Adopt kagent as the base platform.
- `docs/stages/STAGE-07-agent-runtime/README.md` — the stage where most of the lift happens.
- Reference repository: https://github.com/FareedKhan-dev/production-grade-agentic-system
- Reference article: https://levelup.gitconnected.com/building-the-7-layers-of-a-production-grade-agentic-ai-system-37ee5d941f1c
