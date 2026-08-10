# Context Engineering

This document is the platform's doctrine for assembling what enters an agent's context window on every turn. Context engineering is the discipline that replaces prompt engineering as agentic systems mature: the question is no longer "how do I phrase the prompt" but "what *information* is in the context window when the model decides, and how is it structured."

The discipline applies to every layer that touches an agent's context — L1 (gateway-side caching), L3 (system prompts, tool descriptions), L4 (memory retrieval, compaction), L5 (tool inputs and outputs). This document is the cross-layer specification; the layer READMEs link back here.

## The mental model

Context window is RAM. External memory is disk. Good context engineering decides on every turn what belongs in RAM right now and what stays on disk until needed. Stuffing everything into the context window has three failure modes:

1. **Cost and latency spirals** — token cost is per-call, and large contexts inflate every call.
2. **Signal degradation** — models do not weight all tokens equally; the "lost in the middle" effect collapses retrieval accuracy on long contexts even when the model's nominal context window is large enough.
3. **Overflow** — eventually the conversation exceeds even the largest window and the agent loses earlier turns.

The platform treats context-window allocation as a budget. Every turn, the orchestrator decides what fraction of the budget goes to each of the six layers below.

## The six layers of context

A production context window typically contains a mix of:

| # | Layer | Owner in our platform | Token-budget default |
|---|---|---|---|
| 1 | **System instructions** — role, behavioral rules, tool descriptions, output format requirements, few-shot examples | kagent prompt-template ConfigMaps; `Agent` CRD `systemPrompt` field | 8% |
| 2 | **Semantic context** — retrieved chunks via RAG; see `rag-architecture.md` | `memory-svc` Qdrant collection per workload; hybrid search + reranking | 35% |
| 3 | **Operational memory** — long-term, time-aware facts about the world the workload reasons about | `memory-svc` Graphiti-on-FalkorDB; bi-temporal episodes | 12% |
| 4 | **Conversational history** — short-term, the recent turns of this session | `memory-svc` Redis; bounded by token cap, then `session-svc` compacts | 25% |
| 5 | **Retrieval results** — output of tool calls the agent just made | `mcp-sandbox-runner` returns; injected into the LangGraph state | 15% |
| 6 | **Tool access** — the catalog of callable tools and their schemas (descriptions, not bodies) | `mcp-registry` returns the Agent's `toolAllowlist` manifests | 5% |

These percentages are defaults; per-workload tuning is supported via the `Agent` CRD's `contextBudget` field (introduced as a platform extension over the upstream kagent CRD).

## The four dimensions of context engineering

Every context-engineering decision falls into one of four categories. The platform owns the *infrastructure* for each; the agent author owns the *policy*.

### Selection

Which pieces, of all candidates, belong in the next context window?

- **Heuristic-based selection** (the agent's logic; see `heuristic-engineering.md`): "include the last three turns verbatim, summarize anything older."
- **Retrieval-based selection** (RAG; see `rag-architecture.md`): "fetch the top-K chunks for this query from Qdrant via hybrid search."
- **Graph-based selection** (Graphiti episodes): "return all episodes about entity X valid at time T."

### Retrieval

How is the selected information physically fetched and assembled?

- Hybrid search (dense + sparse) + RRF + reranking is the canonical path; see `rag-architecture.md`.
- Graph queries via Graphiti's `search` and `add_episode` APIs.
- Direct lookups via Redis for the short-term tier.

### Compression

When the selected, retrieved information exceeds the budget, how is it shrunk?

- **Sliding-window truncation** for conversation history (oldest turns dropped first).
- **Summarization** for episodes that no longer fit verbatim — `session-svc` calls a fast model to produce a compressed summary, the summary becomes a new episode, the originals stay in Graphiti for audit but are not loaded into context.
- **Selective fact extraction** — for long retrieved chunks, an extraction step pulls only the sentences that match the query, dropping boilerplate.
- **Reranking** as a compression tool — re-rank a top-50 list to a top-5 list.

### Persistence

What gets written back to memory after the turn so future turns can build on it?

- **Episode writes** to Graphiti on every reasoning step that produced a new fact about the world. Bi-temporal: valid time = when the fact is true, ingestion time = when the system learned it. Old facts are not deleted; their `valid_to` is updated.
- **Vector writes** to Qdrant for any new unstructured content the agent generated or ingested.
- **Short-term writes** to Redis for the in-flight session, with a TTL.
- **Checkpoint writes** to Postgres via the LangGraph checkpointer at every node boundary.

## Platform mechanisms that implement the doctrine

| Mechanism | Lives in | Implements |
|---|---|---|
| Hybrid search with RRF + reranking | `memory-svc` → Qdrant | Retrieval (dimension 2) |
| Bi-temporal episodes | `memory-svc` → Graphiti → FalkorDB | Selection (dimension 1), Persistence (dimension 4) |
| Conversation compaction | `session-svc` | Compression (dimension 3) |
| kagent's built-in context compaction | kagent engine | Compression (dimension 3) — used together with `session-svc` for layered compaction |
| LangGraph checkpointer | `agent-orchestrator`, Postgres | Persistence (dimension 4) |
| `Agent.spec.contextBudget` extension | platform-level CRD extension | Selection (dimension 1) — per-workload tuning |
| Tool manifests (descriptions only) | `mcp-registry` | Selection (dimension 1) — tool catalog without tool bodies |

## Anti-patterns we deliberately reject

- **Stuffing the system prompt with every available instruction**. The first turn pays for it forever; we structure system prompts modularly via kagent's prompt-template ConfigMaps and reference fragments by name.
- **Storing prompts and completions in OTel span attributes** (vs span events). Attributes are labels and leak into label cardinality on the metrics side; span events can be dropped or redacted at the Alloy egress. Already enforced by ADR-0006.
- **Single-vector RAG** as the only retrieval strategy. Naive single-vector RAG fails ~40% of the time on retrieval; we require hybrid search + reranking per `rag-architecture.md`.
- **Naive append-everything conversation memory**. Replaced by `session-svc` compaction with sliding-window plus summarization.
- **Tool descriptions inside the conversation** rather than the system prompt. Tool descriptions are stable across turns; they go in the system layer once.

## Cross-references

- `rag-architecture.md` — the retrieval implementation that backs Selection and Retrieval.
- `heuristic-engineering.md` — the agent-side decision logic that drives Selection and Compression triggers.
- `docs/layers/L4-context-and-memory/README.md` — the L4 surface that exposes Selection, Retrieval, Compression, Persistence as APIs.
- `docs/layers/L3-agent-runtime/README.md` — how the agent author consumes those APIs.

## References

- Atlan, "What Is Context Engineering? Complete 2026 Guide": https://atlan.com/know/what-is-context-engineering/
- deepset, "Context Engineering: The Next Frontier Beyond Prompt Engineering": https://www.deepset.ai/blog/context-engineering-the-next-frontier-beyond-prompt-engineering
- Machine Learning Mastery, "Effective Context Engineering for AI Agents" (Google ADK team's reasoning on three-way pressure: cost+latency, signal degradation, overflow).
- Damon McMillan, "Structured Context Engineering for File-Native Agentic Systems" (peer-reviewed, February 2026, 9,649 experiments). Validates that **format choice** (YAML, JSON, Markdown, TOON) has no statistically significant effect on aggregate accuracy; structure and selection matter, syntax does not.
- Neo4j blog, "Why AI Teams Are Moving From Prompt Engineering to Context Engineering" (January 2026): https://neo4j.com/blog/agentic-ai/context-engineering-vs-prompt-engineering/
- Meta Intelligence, "Context Engineering Guide: RAG, Memory Systems & Dynamic Context for Production AI [2026]" (lost-in-the-middle attention blind spot, ~30% information loss prevented via systematic management): https://www.meta-intelligence.tech/en/insight-context-engineering
- QubitTool, "Complete Guide to Context Engineering": https://qubittool.com/blog/context-engineering-complete-guide
