# RAG Architecture

This document specifies the platform's Retrieval-Augmented Generation (RAG) implementation. RAG is the platform's primary mechanism for putting *external* knowledge into an agent's context window. It is one of the four dimensions of context engineering (see `context-engineering.md`), specifically Retrieval and (together with reranking) Selection.

In 2026, RAG has matured into a specific reference architecture. Naive single-vector RAG fails on retrieval roughly 40% of the time. The platform implements the production reference architecture documented across the industry: semantic chunking, hybrid search (dense + sparse with Reciprocal Rank Fusion), reranking, and RAGAS-gated quality.

## The retrieval stack

```
                  agent worker / orchestrator
                            │
                            ▼
                       memory-svc
                            │
        ┌───────────────────┼───────────────────────┐
        ▼                   ▼                       ▼
    Qdrant            FalkorDB (Graphiti)        Redis (short-term)
   dense + sparse      bi-temporal graph         conversation
   collections         episodes                   memory
        │                   │
        ▼                   │
    rerank-svc              │
   (bge-reranker-v2-m3      │
                       │
        │                   │
        └──────────┬────────┘
                   ▼
            top-K final chunks
```

All retrieval goes through `memory-svc`. Agents do not talk to Qdrant or FalkorDB directly.

## Hybrid search

For every external-knowledge retrieval, `memory-svc` issues a hybrid query to Qdrant combining:

- **Dense retrieval**: semantic similarity via embeddings. The platform embedding model: `BAAI/bge-large-en-v1.5` self-hosted (1024-dim). One model, no alternatives, per the one-stack-per-use-case principle.
- **Sparse retrieval**: BM25-style keyword matching. Implemented via Qdrant's sparse vector support using `Qdrant/bm42-all-minilm-l6-v2-attentions` or an equivalent.

The two result sets are merged using **Reciprocal Rank Fusion (RRF)**, which combines rank positions without requiring score normalization. Qdrant supports this natively via `FusionQuery(fusion=Fusion.RRF)`.

A starting alpha (the dense-vs-sparse weighting in implementations that use weighted fusion rather than RRF) of 0.75 (vector-dominant with BM25 correction) is a reasonable default; with pure RRF there is no alpha and the rank fusion is parameter-free.

## Reranking

The top-50 hybrid result set is reranked to a top-K (typical K = 5) using a cross-encoder reranker. The platform reranker is `BAAI/bge-reranker-v2-m3` self-hosted. One model, no alternatives, per the one-stack-per-use-case principle. The reranker runs in `rerank-svc` (see `services/L4-context-and-memory/rerank-svc/`).

Reranking adds 50–150 ms but is the single most cost-effective quality lift in the retrieval stack; we treat it as mandatory.

`rerank-svc` is a thin service hosted alongside `memory-svc` (logical separation; deployable as separate pod for GPU placement). The reranker reads top-50 results and the query, returns top-K with scores.

## Chunking

How content is broken into chunks at ingestion time governs what is retrievable at query time. The platform's chunking policy:

- **Semantic chunking** is the default. Content is split where embedding distance between adjacent passages exceeds a threshold (uses `llama-index`-style or `langchain-experimental`-style semantic splitter). Chunks naturally align with topic boundaries.
- **Fixed-size fallback**: when semantic chunking is not applicable (e.g., transcripts, logs), use 512-token windows with 64-token overlap.
- **Code chunking** for source code: AST-aware splitter that respects function/class boundaries; chunk size up to 2048 tokens.
- **Metadata enrichment**: every chunk carries `source_uri`, `created_at`, `workload_app`, optional `entity_ids` (for Graphiti cross-references), optional `tags`.

The ingestion pipeline lives in `services/L4-context-and-memory/memory-svc/src/ingestion/` (Stage 08).

## Query rewriting

For complex queries, a small fast model rewrites the user's question into one or more retrieval queries. Pattern:

- Decompose multi-intent queries into sub-queries.
- Expand acronyms and ambiguous terms.
- Generate hypothetical document content (HyDE) for very short queries.

Query rewriting is gated by a heuristic (`low-recall-fallback` in `heuristic-engineering.md`): only fires when the first-pass retrieval scores below threshold.

## Agentic RAG (when query rewriting is not enough)

For the hardest queries — multi-intent, multi-hop, cross-document — the platform supports **agentic RAG**. The pattern (Microsoft Azure AI Search agentic retrieval, validated December 2025):

1. The agent (not a separate retrieval service) decomposes the query into sub-queries.
2. Each sub-query goes through the standard hybrid search + rerank stack in parallel.
3. The agent reconciles results across sub-queries.
4. Optionally, the agent calls again with a refined query if the first reconciliation is inadequate.

In our architecture, agentic RAG is just the orchestrator-worker pattern applied to a retrieval task: the lead agent decomposes, subagents run the retrievals via `memory-svc` in parallel, the lead reconciles. No new infrastructure is needed.

Agentic RAG is more expensive than single-pass RAG (sources cite $0.02-0.10/query vs $0.005/query for hybrid+rerank). The orchestrator's `agentic-rag-trigger` heuristic decides per request whether to invoke it (default: only when query contains multi-intent markers detected by a small classifier).

## GraphRAG (for global queries)

Vector retrieval excels at *local* queries ("what does document X say about Y"). It struggles with *global* queries ("summarize the relationships across the entire knowledge base"). Graphiti gives us a partial GraphRAG by virtue of being a knowledge graph; for queries that ask about entity relationships, the agent calls Graphiti directly (via the `graph-for-relations` heuristic) instead of going through hybrid vector retrieval.

We do not currently implement Microsoft GraphRAG-style community-summary precomputation. The Graphiti-on-FalkorDB graph plus the `graph-for-relations` heuristic covers most global-query needs.

## Quality gates: RAGAS

Every retrieval is *evaluated*. The RAGAS framework computes four key metrics:

| Metric | What it measures | Platform threshold |
|---|---|---|
| **Faithfulness** | Whether the answer is grounded in the retrieved context | > 0.90 |
| **Answer Relevancy** | Whether the answer addresses the question | > 0.85 |
| **Context Precision** | Whether retrieved chunks are actually relevant | > 0.80 |
| **Context Recall** | Whether the answer contains all the needed info from context | > 0.75 |

Production: Ragas evaluates a 5% sample of live retrievals via `eval-svc`; scores feed back to Langfuse and Grafana.

CI: Ragas suite runs against golden datasets (`evals/datasets/rag-*.jsonl`) on every PR touching `services/L4-context-and-memory/` or `services/L5-tooling-integration/`. Below-threshold PRs are blocked.

Interpretation guide (Lushbinary 2026): Low Context Precision means fix retrieval; low Faithfulness means fix prompts or add citation enforcement.

## Performance targets

Documented in `docs/layers/L4-context-and-memory/README.md`:

| Operation | p99 |
|---|---|
| Hybrid search over a 1M-chunk Qdrant collection | < 50 ms |
| Rerank top-50 → top-5 with `bge-reranker-v2-m3` self-hosted on CPU | < 150 ms |
| Full retrieval pipeline (hybrid + rerank + memory-svc overhead) | < 250 ms |
| Graphiti graph query for typical relation queries | < 200 ms |

## Cost notes

- Self-hosted embedding + reranking has fixed cost (GPU or CPU node) and zero per-call cost.
- Self-hosted bge-large-en-v1.5 + bge-reranker-v2-m3 is the platform default. We do not offer OpenAI embedding or Cohere rerank as runtime alternatives; that would be the duplicate-stack anti-pattern.
- Agentic RAG multiplies cost by sub-query count; the `agentic-rag-trigger` heuristic exists to keep this bounded.

## Anti-patterns

- **Single-vector retrieval as the only path**. Industry data shows ~40% retrieval failure rate; hybrid + rerank is the floor.
- **Top-K without reranking**. Reranking is the single most cost-effective quality lift; skipping it leaves performance on the table.
- **Fixed-size chunking everywhere**. Semantic chunking is the default; fixed-size is a fallback, not a default.
- **No RAGAS gate in CI**. Without an automated quality gate, retrieval regresses silently. We gate.
- **Tools direct to Qdrant**. Bypassing `memory-svc` skips reranking, governance, telemetry, and per-workload partitioning. Forbidden by NetworkPolicy.

## Cross-references

- `context-engineering.md` — the broader discipline RAG fits inside.
- `heuristic-engineering.md` — `hybrid-first`, `graph-for-relations`, `low-recall-fallback`, `chunk-deduplication`, `agentic-rag-trigger`.
- `harness-engineering.md` — Ragas as part of the harness composition.
- `docs/layers/L4-context-and-memory/README.md` — the L4 surface that exposes RAG operations.

## References

- DEV Community, "RAG Pipelines in Production: Vector Database Benchmarks, Chunking Strategies, and Hybrid Search Data" (April 2026): https://dev.to/pooyagolchian/rag-pipelines-in-production-vector-database-benchmarks-chunking-strategies-and-hybrid-search-data-gbl
- MyEngineeringPath, "Advanced RAG — Hybrid Search, Reranking & Knowledge Graphs (2026)" (March 2026): https://myengineeringpath.dev/genai-engineer/advanced-rag/
- Lushbinary, "RAG Production Guide 2026" (RAGAS thresholds, agentic RAG cost analysis): https://lushbinary.com/blog/rag-retrieval-augmented-generation-production-guide/
- Azure AI Search Agentic Retrieval (Suhas Mallesh, March 2026): https://medium.com/@suhasmallesh/azure-ai-search-advanced-rag-with-terraform-hybrid-search-semantic-ranking-and-agentic-retrieval-fb141ad34c7d
- Qdrant hybrid search reference: https://qdrant.tech/blog/2025-recap/
- Pavan Kumar, "Mastering Chunking for Effective RAG: Beyond Basics with Qdrant and Reranking": https://medium.com/towardsdev/mastering-chunking-for-effective-rag-beyond-basics-with-qdrant-and-reranking-bb0761ae84e4
- Beltsys Labs, "What Is RAG? Complete Guide to Retrieval-Augmented Generation in 2026": https://beltsys.com/en/blog/what-is-rag-complete-guide/
