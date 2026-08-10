# ADR-0004: Graphiti on FalkorDB as the only memory engine for long-term and graph memory

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

Agentic memory has multiple shapes (short-term conversational, semantic vector, long-term temporal-graph). Each shape needs the right backend. We will pick **one** backend per shape. We will not maintain alternatives for the same shape; that is the duplicate-stack anti-pattern.

The L4 layer (Context and Memory) requires:

- **Short-term conversational memory**: Redis (single answer; not contested).
- **Semantic vector memory**: Qdrant (single answer; not contested; chosen because of native hybrid dense+sparse + RRF support per ADR for RAG architecture).
- **Long-term temporal-graph memory**: this is the contested choice this ADR resolves.

For the temporal-graph slot, the production-grade choices in 2026 are:

- **Graphiti** (Apache 2.0, Zep) — bi-temporal knowledge graph engine. Tracks valid time (when a fact is true in the world) and ingestion time (when the system learned it). Designed for agentic memory specifically.
- **Mem0** — simpler vector-based memory with framework integrations (CrewAI, LangGraph, Flowise). No temporal reasoning. Lower memory footprint per conversation.

Graphiti supports three graph backends:

- **FalkorDB** (BSD-3, Redis-based, Cypher-compatible) — the platform's choice.
- **Neo4j** (GPL on the community edition; commercial-license friction for derived works).
- **Kuzu** (MIT) — embedded single-process engine; does not fit a multi-service architecture.

## Decision

The platform uses **Graphiti on FalkorDB** as the only engine for long-term and graph memory.

- **No Mem0.** Removed entirely from the architecture. The reference workload's `mem0ai` import is replaced during the Stage 07 port with calls to `memory-svc /episodes` and `memory-svc /retrieve`.
- **No Neo4j.** Rejected on license grounds.
- **No Kuzu.** Rejected as embedded-only.
- **FalkorDB is the Graphiti backend.** Configured as a Redis-protocol service in `platform/L4-data-plane/falkordb/`.

The platform exposes long-term memory through `memory-svc` regardless of which model the agent uses. Agents never call FalkorDB directly. The bi-temporal model is the contract: when a fact becomes invalid, set `valid_to`; queries default to the current valid window.

## Consequences

Positive:

- One temporal-graph backend, one Graphiti integration, one operational runbook for FalkorDB. No "which backend serves this workload" decision per agent.
- Temporal reasoning is the default. Agents reasoning about a changing world get bi-temporal validity for free, without opt-in configuration.
- BSD-3 license on FalkorDB removes commercial-license friction.
- Cypher compatibility means standard graph query patterns work.
- Active maintenance by Zep (Graphiti) and FalkorDB teams; both shipped 2026 releases.

Negative:

- Higher memory footprint than Mem0 (Graphiti is more expressive). We mitigate by:
  - Running Graphiti for long-term episodes only; short-term conversation memory stays in Redis.
  - Configuring entity-resolution thresholds to avoid duplicate-node sprawl.
  - Running compaction jobs nightly to consolidate redundant episodes.
- Operating a graph database is a new operational responsibility for the platform team. FalkorDB inherits Redis backup primitives (RDB + AOF); we configure both.
- We carry no fallback option for Mem0-style workloads. Workloads that only need vector memory bypass the graph through `memory-svc /vectors/*` instead of `memory-svc /episodes/*`.

Neutral:

- FalkorDB has a Helm chart; deployment is standard.

## Alternatives considered

- **Mem0 only**: rejected because no temporal reasoning, and the L4 requirement explicitly includes "context handling across turns and across agents" with consistency across time.
- **Both Graphiti and Mem0 (per-workload selectable)**: rejected as the duplicate-stack anti-pattern. Two memory backends doubles the operational and testing surface for no architectural benefit.
- **Graphiti on Neo4j**: rejected on license grounds for derived works.
- **Graphiti on Kuzu**: rejected because Kuzu is embedded; we need a service multiple processes can address.
- **GraphRAG (Microsoft Research)**: rejected because it precomputes summaries via repeated LLM calls and does not support dynamic update or temporal invalidation. The Graphiti graph plus the `graph-for-relations` heuristic from `docs/protocols/heuristic-engineering.md` covers most global-query needs without precomputation.

## References

- Graphiti open source: https://www.getzep.com/product/open-source/
- Graphiti paper (arXiv 2501.13956): https://arxiv.org/abs/2501.13956
- FalkorDB: https://www.falkordb.com/
- FalkorDB GitHub (BSD-3): https://github.com/FalkorDB/FalkorDB
- Neo4j developer blog on Graphiti (lists FalkorDB and Kuzu as supported backends, used here only for context, not as endorsement of Neo4j): https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/
- 2026 agent memory comparison (Mem0 vs Zep/Graphiti; informs the rejection of Mem0 for this platform): https://blog.devgenius.io/ai-agent-memory-systems-in-2026-mem0-zep-hindsight-memvid-and-everything-in-between-compared-96e35b818da8
