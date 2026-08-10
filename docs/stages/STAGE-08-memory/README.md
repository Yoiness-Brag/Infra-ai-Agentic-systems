# Stage 08 — Memory (L4 service plane)

## Goal

Stand up `memory-svc`, `session-svc`, and `rerank-svc` on top of the Stage 02 stores. Implement the unified memory API; integrate Graphiti against FalkorDB; wire the per-workload Qdrant collection pattern with hybrid dense+sparse search and Reciprocal Rank Fusion; implement compaction; implement the cross-encoder reranking stage. After this stage the platform's RAG pipeline (`POST /retrieve`) is production-ready.

## Depends on

Stage 02 (data stores: Postgres, Qdrant, FalkorDB, Redis, ClickHouse, MinIO) and Stage 07 (agent-orchestrator and agent-worker, which call memory-svc).

## Deliverables

- `services/L4-context-and-memory/memory-svc/` with the HTTP API:
  - `POST /episodes` (Graphiti add_episode)
  - `GET /episodes/search`
  - `POST /vectors`, `GET /vectors/search`
  - **`POST /retrieve`** — the platform RAG endpoint: hybrid (dense + sparse) → RRF → call to rerank-svc → top-K
  - `GET /session/{id}`, `PUT /session/{id}`
  - `POST /sessions/{id}/compact`
- `services/L4-context-and-memory/session-svc/` with the compaction worker (sliding-window truncation, summarization via small fast model, selective promotion to Graphiti).
- `services/L4-context-and-memory/rerank-svc/` with the cross-encoder reranker. Default `BAAI/bge-reranker-v2-m3` self-hosted; CPU is acceptable for the target throughput (~150 ms p99 on top-50). Deployable as a separate pod for optional GPU placement.
- Graphiti client configured for FalkorDB with the per-workload `group_id` partitioning pattern.
- Qdrant collection provisioning: one collection per workload with dense (1024-dim `bge-large-en-v1.5`) + sparse (`bm42-all-minilm-l6-v2-attentions`) configuration.
- NATS consumer for `memory.ingest.<workload>` for asynchronous writes.
- Updates to `agent-orchestrator` and `agent-worker` to call `memory-svc /retrieve` instead of going direct to Qdrant.
- Initial AsyncAPI specs for `memory.ingest.*` and OpenAPI for the memory-svc HTTP surface in `shared/proto/`.

## Non-goals

- No agentic RAG yet; that pattern emerges naturally in Stage 12 from the orchestrator-worker pattern + the heuristic catalog and does not need separate infrastructure here.
- No multi-region memory replication; single-region until proven necessary.

## Acceptance criteria

1. Write-then-read roundtrip works for all four backends through memory-svc (Graphiti episode, Qdrant vector, Redis session, LangGraph checkpoint).
2. `POST /retrieve` end-to-end p99 under 250 ms with the SLO matrix from `docs/layers/L4-context-and-memory/README.md`.
3. Reranking lifts measurable retrieval quality on the Stage 12 golden datasets vs no-rerank baseline; Ragas Faithfulness > 0.90 on at least one canonical dataset.
4. Compaction reduces a 32K-token conversation to under 8K with a fidelity check that survives an LLM-as-judge faithfulness rubric.
5. Langfuse traces show memory operations as child spans of agent runs with the full GenAI semconv attribute set.
6. NetworkPolicy denies direct workload-pod access to Qdrant; only memory-svc is allowed.

## Next stage

Stage 12 (Evaluation) — the four-tool harness lands and starts asserting RAGAS thresholds against `/retrieve` outputs in CI.

## See also

- `docs/layers/L4-context-and-memory/README.md` — the L4 specification with full SLOs and contracts.
- `docs/protocols/rag-architecture.md` — the doctrine this stage implements.
- `docs/protocols/context-engineering.md` — the broader context discipline.
- ADR-0004: Graphiti on FalkorDB.
