# Documentation contradictions & gaps

Found during the Stage-00 full-doc review (2026-06-02). ADRs are authoritative; where a layer/stage
doc disagrees with an ADR, the doc is the bug. Resolve P0/P1 before building the affected layer.

### [DOC-01] Vanilla `otel-collector` endpoint contradicts ADR-0006 (Alloy is the only collector)
- **Status:** todo · **Priority:** P0 · **Stage:** 03 · **Refs:** ADR-0006; `docs/layers/L1,L2,L3,L5/README.md`; `docs/protocols/otel-genai-semconv.md`; `docs/overview/01-design-principles.md`
- L1/L2/L3/L5 docs hardcode OTLP target `otel-collector.ai-observability:4317` and several docs say
  "OTel Collector" as the deployed component, but ADR-0006 forbids the vanilla OTel Collector and
  makes **Alloy** the sole collector. **Decide the canonical Service name** (likely Alloy exposed as
  a Service literally named `otel-collector` for drop-in OTLP) and pin it everywhere. Update docs to
  say "Alloy (OTLP receiver)".

### [DOC-02] `kube-prometheus-stack` references contradict ADR-0006
- **Status:** todo · **Priority:** P1 · **Stage:** 03 · **Refs:** ADR-0006; `docs/reference/upstream-repo-mapping.md` (lines ~39, ~55); `docs/layers/L7-.../README.md`
- `upstream-repo-mapping.md` routes `prometheus.yml` + reference histograms to
  `platform/L7-observability/kube-prometheus-stack/values.yaml` and "ServiceMonitors", but ADR-0006
  says kube-prometheus-stack is **not** deployed (Alloy scrapes the same endpoints). Update the
  mapping to target Alloy scrape config.

### [DOC-03] `tools.invoke.*` NATS subject has no stream / AsyncAPI spec
- **Status:** todo · **Priority:** P1 · **Stage:** 04 · **Refs:** ARCHITECTURE.md; ADR-0007; `docs/stages/STAGE-04-message-bus/README.md`; `docs/layers/L2-.../README.md`
- ARCHITECTURE/ADR-0007 define `tools.invoke.<tool>.<session_id>`, but Stage 04 creates only four
  streams (`agents.subtask`, `agents.result`, `memory.ingest`, `audit`) and L2 lists four. Either add
  a stream + AsyncAPI contract for tool-invoke, or document that tool calls are synchronous (not via
  NATS) and remove the subject.

### [DOC-04] `agentic-rag-trigger` heuristic referenced but absent from catalog
- **Status:** todo · **Priority:** P2 · **Stage:** cross-cutting · **Refs:** `docs/protocols/rag-architecture.md` (~84, ~124); STAGE-08/12; `docs/protocols/heuristic-engineering.md`
- Add `agentic-rag-trigger` to the heuristic catalog (with metric + threshold + DeepEval test) or
  remove the references.

### [DOC-05] kagent CRD extension fields lack an ADR
- **Status:** todo · **Priority:** P1 · **Stage:** 06 · **Refs:** `heuristic-engineering.md` (`Agent.spec.maxSubtasks`); `context-engineering.md` (`contextBudget`); ARCHITECTURE (`maxSteps`,`runDeadline`,`tokenBudget`,`costBudgetUsd`); `docs/layers/L3-.../README.md`
- Platform extends the upstream CNCF kagent Agent CRD with extra fields, but no ADR records the
  mechanism (CRD fork? validating admission? annotations?). Doctrine says a default budget that
  affects a public contract needs an ADR. Write it; reconcile L3 README's field list with ARCHITECTURE.

### [DOC-06] Audit ledger write-path under-specified (two writers for one table)
- **Status:** todo · **Priority:** P2 · **Stage:** 11 · **Refs:** `docs/layers/L6-.../README.md`; STAGE-11; `platform/L7-observability/langfuse/audit-schema.sql`
- `platform_audit` is written via both "the OTel Collector audit branch" and "Langfuse Worker".
  Pin the single canonical writer and path; fix the "audit-mode-off enforcement" wording in Stage 11.

### [DOC-07] HITL audit subject naming doesn't fit the `audit.<service>.<action>` pattern
- **Status:** todo · **Priority:** P3 · **Stage:** 04 · **Refs:** glossary, L3, heuristics vs ADR-0007
- `audit.hitl.<workload>` doesn't match `audit.<service>.<action>`. Reconcile the scheme.

### [DOC-08] Embedding/reranker compute placement (GPU/CPU node pool) unspecified
- **Status:** todo · **Priority:** P2 · **Stage:** 08 · **Refs:** `rag-architecture.md`; `docs/layers/L4-.../README.md`; STAGE-08
- No stage provisions GPU/CPU node pools for self-hosted bge-large / bge-reranker. Specify node
  placement + resource requests in Stage 08 (and Stage 01 if a node pool is needed).

### [DOC-09] Production TLS issuer unspecified (only Let's Encrypt staging mentioned)
- **Status:** todo · **Priority:** P3 · **Stage:** 03/14 · **Refs:** `docs/layers/L1-.../README.md`; STAGE-03/14
- cert-manager uses LE staging in Stage 03; the production ClusterIssuer for K3s-on-EC2 is never
  named. Define it for Stage 14.

### [DOC-10] MinIO / ClickHouse are "canonical" but un-ADR'd
- **Status:** todo · **Priority:** P3 · **Stage:** cross-cutting · **Refs:** glossary; ADR-0002
- They appear in layer/stage/glossary docs but no decision record locks them. Optional: a short ADR
  for completeness, or note them as non-contested in ADR-0002.

### [DOC-11] Verify FLOW.mmd diagrams against the prose contracts
- **Status:** todo · **Priority:** P3 · **Stage:** cross-cutting · **Refs:** all `docs/layers/*/FLOW.mmd`, `docs/stages/*/FLOW.mmd`
- The doc review covered READMEs only; `*.mmd` flow diagrams were not cross-checked against the
  (now-corrected) component names/endpoints. Do a diagram pass after DOC-01/02 land.
- **RESOLVED 2026-06-02** — the deep atomic review (round 2) cross-checked all 10 Mermaid diagrams.
  All parse as valid Mermaid; concrete diagram/prose mismatches are filed below as DOC-18, DOC-19,
  DOC-26, DOC-27, DOC-35, and the P3 diagram-polish batch (DOC-40).

---

# Round 2 — deep atomic file-by-file review (2026-06-02)

Found by a 7-agent parallel swarm reviewing all 60 doc/diagram files individually. Deduplicated
across agents. DOC-01..11 above are NOT repeated here. **DOC-06 update:** the two-writer audit
conflict now has concrete file refs — `platform/L4-data-plane/clickhouse/README.md:43` (Alloy writes
direct) vs `docs/layers/L6-safety-policy-governance/FLOW.mmd:72` + `…/README.md:88` (Langfuse Worker
writes); pick one writer.

## P0

### [DOC-12] ARCHITECTURE.md ships a second agent runtime (Go ADK), violating Python-ADK-only
- **Status:** todo · **Priority:** P0 · **Stage:** 06/07 · **Refs:** `ARCHITECTURE.md:23,37` vs `docs/adr/0011-base-platform-kagent.md:37,74`, `README.md:168,193`
- ARCHITECTURE says kagent is "multi-runtime (Python ADK ~15s; Go ADK ~2s)" and exposes Go ADK
  per-agent via a `runtime` field. ADR-0011 and README mandate **Python ADK only, Go ADK not
  deployed**. The ADR is authoritative → fix ARCHITECTURE.md (remove the Go-ADK runtime path) or
  supersede ADR-0011 with a new ADR if dual-runtime is actually wanted. Highest-priority because it
  breaks the one-stack-per-concern spine in a primary doc.

## P1

### [DOC-13] pgvector simultaneously banned and in-use
- **Status:** todo · **Priority:** P1 · **Refs:** `README.md:194` (bans pgvector) vs `docs/overview/00-platform-overview.mmd:33` ("PG 16 + pgvector + CNPG") and `docs/overview/02-glossary.md:139` ("Used by the LangGraph checkpointer"). ARCHITECTURE.md omits pgvector (sides with the ban). Decide: is pgvector used by the checkpointer or not? Fix the .mmd + glossary or the ban.

### [DOC-14] ADR index titles drop the load-bearing "only"
- **Status:** todo · **Priority:** P1 · **Refs:** `docs/adr/README.md:12` (0004) and `:18` (0010)
- Index titles omit "only" present in the ADR H1s ("…the **only** memory engine", "K3s as the
  **only** cluster substrate"), misrepresenting single-stack scope in the canonical index.

### [DOC-15] harness-engineering cites RAGAS thresholds "per ADR-0006" but ADR-0006 has none
- **Status:** todo · **Priority:** P1 · **Refs:** `docs/protocols/harness-engineering.md:67`; `docs/adr/0006-*.md`
- Thresholds (0.90/0.85/0.80/0.75) only exist in `rag-architecture.md`. Drop the ADR-0006 citation or add the thresholds to an ADR.

### [DOC-16] harness-engineering repo-layout block is fictional
- **Status:** todo · **Priority:** P1 · **Refs:** `docs/protocols/harness-engineering.md:22-57`
- Describes an eval-svc `src/`+`prompts/` tree and top-level `evals/{ragas-suites,promptfoo,inspect-suites}` + `*.jsonl` that do not exist; the real evaluator code lives at `production-grade-agentic/evals/`. Rewrite to match reality (and DOC-12-scope: that code is reference-only).

### [DOC-17] CI references eval dirs that do not exist (commands would fail)
- **Status:** todo · **Priority:** P1 · **Refs:** `evals/README.md:11-13`, `services/L7-evaluation/eval-svc/README.md:52-54`, `.github/workflows/README.md:21`
- `evals/promptfoo/`, `evals/ragas-suites/`, `evals/inspect-suites/` are invoked by CI but absent (only `datasets/`, `deepeval-suites/`, `metrics/` exist). Create the dirs or fix the commands.

### [DOC-18] L3 FLOW.mmd omits a2a-adapter and the entire A2A path
- **Status:** todo · **Priority:** P1 · **Refs:** `docs/layers/L3-agent-runtime/FLOW.mmd` vs `README.md:27,36-40`
- a2a-adapter is a listed L3 Service with a full contract subsection, but appears nowhere in the diagram.

### [DOC-19] L4 FLOW.mmd omits rerank-svc and `POST /retrieve`
- **Status:** todo · **Priority:** P1 · **Refs:** `docs/layers/L4-context-and-memory/FLOW.mmd` vs `README.md:26,40,66`
- rerank-svc (a named L4 Service + pipeline step 3) and the headline `POST /retrieve` RAG endpoint are absent; diagram shows only `GET /vectors/search`. The layer's main RAG path is undrawn.

### [DOC-20] "read context handle" verb has no L4 endpoint
- **Status:** todo · **Priority:** P1 · **Refs:** `docs/layers/L2-*/FLOW.mmd:29`, `docs/layers/L3-*/FLOW.mmd:27` vs L4 README API table (`/episodes/search`,`/vectors/search`,`/retrieve`,`/session`)
- Both L2 and L3 diagrams call memory-svc "read context handle", an operation the L4 contract does not expose. Define the endpoint or rename to an existing one.

### [DOC-21] rerank-svc README mislocates its Helm chart under platform/
- **Status:** todo · **Priority:** P1 · **Refs:** `services/L4-context-and-memory/rerank-svc/README.md:28,38-42`
- Claims chart at `platform/L4-data-plane/rerank-svc/` (nonexistent; L4-data-plane is 6 stores). rerank-svc is a `services/` component — breaks folder discipline.

### [DOC-22] OPA constraint gates on an undefined `tools-*` namespace
- **Status:** todo · **Priority:** P1 · **Refs:** `platform/L6-governance/opa-gatekeeper/README.md:12`, `platform/runtime-classes/README.md:28` vs `platform/namespaces/README.md`
- `RequireCubeRuntimeClassInTools` targets `tools-*`, but the canonical namespace list has no such namespace (sandboxes run in `cube-system`). The constraint can never match.

### [DOC-23] L7 CI hook omits Promptfoo from the four-tool harness
- **Status:** todo · **Priority:** P1 · **Refs:** `docs/layers/L7-observability-reliability/README.md:78` vs `:31`, `FLOW.mmd:38`, `harness-engineering.md`
- CI invocation lists only DeepEval/Ragas/Inspect AI; Promptfoo (one of the mandated four) is dropped.

### [DOC-24] L5→L4 "persist artifacts as memory handles" has no L4 endpoint
- **Status:** todo · **Priority:** P1 · **Refs:** `docs/layers/L5-*/FLOW.mmd:43`, `…/README.md:61,81` vs L4 API table
- L5 describes persisting artifact handles to memory-svc; L4 exposes no artifact/handle endpoint.

## P2

### [DOC-25] ADR-0002 layer label "Context and Memory" vs folder `L4-data-plane`
- **Status:** todo · **Priority:** P2 · **Refs:** `docs/adr/0002-*.md:22-23` vs `0004-*.md:34`, `README.md:224`. Folder name doesn't carry the ADR-0002 layer name.

### [DOC-26] Langfuse backing-store / trace-writer topology disagrees across diagrams
- **Status:** todo · **Priority:** P2 · **Refs:** `README.md:142-145` & `docs/overview/00-platform-overview.mmd:109` (Web writes to CH; only 1 vs 3 Langfuse edges); `docs/layers/L7-*/FLOW.mmd:63-64` + `platform/L7-observability/langfuse/README.md:47` (Worker writes). Pin who writes traces to ClickHouse and the full Langfuse edge set.

### [DOC-27] Grafana has no folder home
- **Status:** todo · **Priority:** P2 · **Refs:** `platform/L7-observability/README.md:31`, `grafana-dashboards/README.md`
- Grafana is deployed + referenced as a datasource but there is no `platform/L7-observability/grafana/` dir/README declaring its install/values.

### [DOC-28] heuristic metric-family contradiction (`heuristic.<name>` vs actual names)
- **Status:** todo · **Priority:** P2 · **Refs:** `docs/protocols/heuristic-engineering.md:91` vs catalog rows `:27-77`
- Doc says every heuristic increments `heuristic.<name>`, but catalog metrics use `orchestrator.dispatch.*`, `model.route.*`, `run.*_hit.count`, etc. Dashboards keyed on `heuristic.*` would be empty.

### [DOC-29] Heuristic regression suite filename mismatch
- **Status:** todo · **Priority:** P2 · **Refs:** `harness-engineering.md:46,107` (`test_heuristics.py`) vs `heuristic-engineering.md:97,108` (`heuristics.py`).

### [DOC-30] Stage-11 "audit-mode-off enforcement" is garbled
- **Status:** todo · **Priority:** P2 · **Refs:** `docs/stages/STAGE-11-governance/README.md:6`
- Gatekeeper `enforcementAction` is `audit`/`deny`/`warn`; "audit-mode-off enforcement" is self-contradictory. Likely means "now enforcing (deny), no longer audit-only".

### [DOC-31] Stage-02 "seven stores" vs six enumerated
- **Status:** todo · **Priority:** P2 · **Refs:** `docs/stages/STAGE-02-data-plane/README.md:24` vs `:13-14`
- AC says "all seven stores Ready"; only six are named (Postgres, Qdrant, FalkorDB, Redis, ClickHouse, MinIO). Clarify whether Langfuse's Postgres/Redis are separate instances.

### [DOC-32] Stage-09 cold-start AC (<200ms p99) contradicts platform sub-60ms claim
- **Status:** todo · **Priority:** P2 · **Refs:** `docs/stages/STAGE-09-tools-and-sandbox/README.md:26` vs `README.md:170,198`, `ARCHITECTURE.md:84`
- Acceptance bar is >3× looser than the stated CubeSandbox capability. Align the number.

### [DOC-33] L1 README "single component" vs lists 3
- **Status:** todo · **Priority:** P2 · **Refs:** `docs/layers/L1-interface-and-entry/README.md:11` vs `:29-32` (Kong + cert-manager + Ingress/LB).

### [DOC-34] A2A ingress: bypasses Kong (master diagram) vs routes through Kong `/a2a/*`
- **Status:** todo · **Priority:** P2 · **Refs:** `README.md:77` vs `platform/L1-gateway/README.md:10-11`, `kong/README.md:56`. Decide whether A2A inbound traverses the gateway perimeter.

### [DOC-35] L6 FLOW under-enumerates OPA constraints
- **Status:** todo · **Priority:** P2 · **Refs:** `docs/layers/L6-*/FLOW.mmd:29-36` (5 shown) vs `opa-gatekeeper/README.md` (7; adds `RequireAgentResourceBounds`, `RequireOTelInstrumentation`/SidecarOrSDK). Also `ai-semantic-cache` node in FLOW not in README L1-enforcement row.

### [DOC-36] MinIO presence differs between the two whole-system diagrams
- **Status:** todo · **Priority:** P2 · **Refs:** `README.md:71,145` (MinIO node + media edge) vs `docs/overview/00-platform-overview.mmd` (no MinIO). Reconcile the canonical C4 with the README mega-diagram.

## P3 — editorial / diagram polish (batch)

### [DOC-40] P3 batch — low-severity precision/editorial fixes
- **Status:** todo · **Priority:** P3 · one item per bullet:
  - `docs/overview/02-glossary.md:107` — LGTM-P "new in this revision" vs "from day one" self-tension.
  - `README.md:80` vs `00-platform-overview.mmd:66` — Kong route label `/chat/stream` vs `/chat/*`.
  - `docs/overview/00-platform-overview.md:7`, `docs/adr/0003-*.md:49`, `0005-*.md:11` — dangling/garbled "Excalidraw design" references in prose.
  - `docs/adr/0008-*.md:68` — bare "Argo Rollouts canary documentation." citation with no URL.
  - `heuristic-engineering.md:68` vs `mcp.md:28` — `tool.timeout_ms` vs manifest field `timeout_ms`.
  - `docs/layers/L1-*/FLOW.mmd:9` — orchestrator labeled `(L3)` with no L2-role note.
  - `docs/layers/L4-*/FLOW.mmd:50-52` — edges mix subgraph-id and node-id as source (ambiguous).
  - `docs/layers/L5-*/FLOW.mmd:17-21,27-30` — two `alt` blocks lack `else`/return (fall-through).
  - `docs/layers/L7-*/FLOW.mmd:3` — subgraph titled "Emit sources L1 to L6" but no L6 emit node.
  - `docs/layers/L3-*/FLOW.mmd:37` vs `README.md:65` — HITL `audit.hitl.<workload>` emit-path missing from diagram (relates to DOC-07).
  - `docs/stages/README.md:14,23` — index under-specifies deps (03←02, 12←08); `STAGE-04:30` 04→07 back-edge not mirrored.
  - `platform/L7-observability/langfuse/README.md:49` vs `redis/README.md:7-13` — Langfuse uses Redis `db=4`, not in the canonical db 0–3 table.
  - `platform/namespaces/README.md:17,37` vs `README.md:52` — CubeShim listed as a cube-system pod in master/C4 but absent from cube-system namespace contents (4 vs 5 parts).
