# Layer 4 — Context and Memory

## Purpose

L4 gives agents memory that survives a single context window, survives a single pod restart, and survives the lifetime of a conversation. It exposes a single internal API (`memory-svc`) over four backends — temporal knowledge graph (Graphiti on FalkorDB), vector store (Qdrant), short-term cache (Redis), and workflow checkpoints (Postgres). L4 also owns conversation compaction (`session-svc`) and the RAG retrieval stack (hybrid search, reranking) that backs the **Retrieval** dimension of context engineering.

L4 does not contain reasoning logic. It does not call LLMs (the *retrieval reranker* is a cross-encoder, not a generator). It stores, retrieves, summarizes, and invalidates. Any heuristic about what to remember belongs to the agent, not to memory-svc — see `docs/protocols/heuristic-engineering.md`.

## Components

**Platform** (data stores):

| Component | Purpose |
|---|---|
| **FalkorDB** | Backend for Graphiti's temporal knowledge graph. BSD-3, Redis-based, Cypher-compatible. |
| **Qdrant** | Vector store with native hybrid search (dense + sparse) and RRF fusion. |
| **Redis** | Short-term conversation memory; idempotency dedup; Kong rate-limit and semantic-cache backing. Single deployment, multiple logical databases. |
| **Postgres** | LangGraph checkpoints (via `langgraph-checkpoint-postgres`); per-workload row-level-security-scoped application data; Langfuse metadata. |

**Services**:

| Service | Purpose |
|---|---|
| **memory-svc** | Unified memory API. Wraps Graphiti + Qdrant + Redis behind one HTTP surface so that agents do not know which backend serves a given call. Implements the hybrid-search retrieval pipeline. |
| **session-svc** | Conversation compaction: summarization of long histories, sliding-window truncation, selective promotion of episodes from short-term to long-term memory. |
| **rerank-svc** | Cross-encoder reranker. Default `BAAI/bge-reranker-v2-m3` self-hosted. Logical separation from memory-svc (separate pod for GPU placement when applicable). |

## Contracts

### Upstream API (what L3 calls)

`memory-svc` exposes the platform memory API. All endpoints under `/memory/`:

| Endpoint | Purpose |
|---|---|
| `POST /episodes` | Write an episode to Graphiti (Graphiti's `add_episode` semantics; bi-temporal). |
| `GET /episodes/search` | Query by entity, time window, or relation. Returns episode handles. |
| `POST /vectors` | Write a vector with metadata to Qdrant. |
| `GET /vectors/search` | Single-mode vector search; top-K with scores. |
| `POST /retrieve` | **The platform RAG endpoint.** Runs hybrid search (dense + sparse + RRF) + reranking; returns top-K reranked chunks. The endpoint most agent workers call. |
| `GET /session/{session_id}` | Read short-term session memory from Redis. |
| `PUT /session/{session_id}` | Write short-term session memory; TTL-bounded. |
| `POST /sessions/{session_id}/compact` | Trigger compaction via `session-svc`. |

All endpoints accept an `X-Workload-App` header that scopes the request. Backing stores partition on this header (Graphiti group_id, Qdrant collection name, Redis key prefix, Postgres RLS predicate).

### Asynchronous ingestion

NATS subject `memory.ingest.<workload_app>` carries asynchronous episode writes. `memory-svc` runs a consumer that fan-ingests into Graphiti and Qdrant.

### Downstream contracts

- FalkorDB via Redis protocol on port 6379 (separate from the platform Redis instance).
- Qdrant via gRPC on port 6334 (preferred) or HTTP on port 6333.
- Redis (platform) via RESP protocol.
- Postgres via libpq with TLS.

## The retrieval pipeline (the RAG specifics)

See `docs/protocols/rag-architecture.md` for the full doctrine. Operational summary:

1. Agent calls `POST /retrieve` with the query and a `mode` (`hybrid` default, `graph`, `vector_only`, `keyword_only`).
2. `memory-svc` executes the configured mode:
   - **Hybrid**: simultaneous dense (embedding) + sparse (BM25-like) queries to Qdrant; RRF fusion via `FusionQuery(fusion=Fusion.RRF)`. Returns top-50.
   - **Graph**: Cypher query over Graphiti for entity-relation lookups.
3. `rerank-svc` reranks top-50 → top-K using `bge-reranker-v2-m3` (default).
4. Optional metadata enrichment (entity cross-refs to Graphiti episodes).
5. Return top-K with scores, source URIs, and chunk content.

Platform embedding model: `BAAI/bge-large-en-v1.5` self-hosted (1024-dim). One model, no per-workload override (see ADR-0004 and the one-stack-per-use-case principle).

Default sparse model: `Qdrant/bm42-all-minilm-l6-v2-attentions` or equivalent BM25 implementation.

Chunking policy: semantic chunking by default; 512-token / 64-overlap fixed-size fallback; AST-aware chunking for source code. Documented in `docs/protocols/rag-architecture.md`.

## Quality gates (RAGAS)

Production retrieval is sampled at 5% and scored via Ragas. Thresholds (also asserted in CI on golden datasets):

- Faithfulness > 0.90
- Answer Relevancy > 0.85
- Context Precision > 0.80
- Context Recall > 0.75

Below-threshold PRs are blocked. Production regression alerts fire on 10% rolling-window drops.

## Distributed-system properties (L4 commitments)

- **Per-workload partitioning** enforced at memory-svc, not at the agent layer.
- **Eventual consistency** between asynchronous writes (NATS `memory.ingest.*`) and synchronous reads. Workloads needing read-your-write semantics use `POST /episodes` synchronously.
- **Compaction policy** configurable per workload. Defaults: compact at 8K tokens, summarize the oldest 4K, retain the most recent 4K verbatim.
- **Entity-resolution thresholds** for Graphiti are tunable; defaults follow upstream Graphiti.
- **Episode invalidation**: Graphiti bi-temporal model. When a fact becomes invalid, set `valid_to` rather than deleting; queries default to the current valid window.
- **Vector lifecycle**: Qdrant points carry `created_at` and optional `expires_at`; a periodic job deletes expired points.
- **Per-pod hybrid-search dedup**: identical queries within a short window de-dup via Redis idempotency key (heuristic: `chunk-deduplication` from `heuristic-engineering.md`).

## Service-level objectives

| SLO | Target |
|---|---|
| `POST /retrieve` end-to-end p99 (hybrid + rerank) | < 250 ms |
| Hybrid search over a 1M-chunk Qdrant collection p99 | < 50 ms |
| Reranking top-50 → top-5 p99 (CPU) | < 150 ms |
| Graphiti graph query p99 | < 200 ms |
| Redis short-term read p99 | < 5 ms |
| LangGraph checkpoint write p99 | < 50 ms |
| Compaction job runtime p99 for 32K-token conversation | < 60 s |
| memory-svc availability | 99.9% |

## Out of scope

- Reasoning. Belongs to L3.
- Decisions about what to remember (which heuristic to apply). Codified in `docs/protocols/heuristic-engineering.md`; the agent chooses, memory-svc executes.
- Telemetry storage. Belongs to L7.
- Policy on PII storage. Enforcement is at L1 (sanitization) and at L7 (Alloy OTTL redaction); L4 trusts that incoming writes have been pre-sanitized.

## See also

- ADR-0004: Graphiti on FalkorDB.
- `docs/protocols/context-engineering.md` — the discipline that drives L4 usage patterns.
- `docs/protocols/rag-architecture.md` — the hybrid-search + RRF + rerank stack in depth.
- `docs/protocols/heuristic-engineering.md` — `hybrid-first`, `graph-for-relations`, `low-recall-fallback`, `chunk-deduplication`.
- `FLOW.mmd` — read and write flows through memory-svc, including the RAG path.
- `components.md` — backend configuration matrix; Graphiti group_id strategy; Qdrant collection layout.
- `runbook.md` — deploy stores, run compaction manually, recover from FalkorDB crash, restore from Redis RDB.

## Status

Documentation contract in place at Stage 00. Postgres + Qdrant + Redis land at Stage 02. FalkorDB lands at Stage 02. memory-svc, session-svc, rerank-svc land at Stage 08.
