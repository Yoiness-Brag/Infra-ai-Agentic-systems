# .backlog — project backlog

Plain-markdown, version-controlled backlog. One file per theme; each item has an ID, status, and
priority so it survives across sessions and is greppable.

## Item format

```
### [<ID>] <title>
- **Status:** todo | in-progress | blocked | done
- **Priority:** P0 (blocker) | P1 (high) | P2 (normal) | P3 (low)
- **Stage:** <00..14 or "cross-cutting">
- **Refs:** <files / ADRs / docs>

<description + acceptance criteria>
```

## ID prefixes

| Prefix | Theme | File |
|---|---|---|
| `DOC-*`  | Documentation contradictions / gaps (must fix before building on them) | `doc-contradictions.md` |
| `REF-*`  | Reference-port (`production-grade-agentic/`) defects to fix in Stage 07 | `reference-port-review.md` |
| `S01-*`  | Stage 01 — cluster provisioning (next up) | `stage-01-cluster-provisioning.md` |

## Reference docs (comprehension, not backlog items)

| Doc | What it is |
|---|---|
| `build-understanding.md` | What we are building — thesis, agentic runtime model, 5 doctrines, 7 layers, 15-stage roadmap, first-usable milestone, exclusions. Read this to orient before building. |
| `k8s-requirements.md` | Kubernetes/infra deployment-requirements catalog — cluster/namespaces/CRDs/workloads/networking/security/autoscaling/GitOps/storage + 10 open deployment-spec gaps. |

## Current focus

> `doc-contradictions.md` now holds **37 findings** (round 1 = DOC-01..11; round 2 deep atomic
> 7-agent review = DOC-12..36 + the DOC-40 P3 batch). All 10 Mermaid diagrams parse cleanly.

1. Resolve **P0/P1 DOC-*** items — they pin canonical names/paths the build depends on. Start with
   **DOC-12 (P0:** ARCHITECTURE Go-ADK vs Python-ADK-only), then the Alloy-vs-`otel-collector`
   naming (`DOC-01`) and pgvector ban-vs-use (`DOC-13`).
2. Begin **Stage 01** (`S01-*`) — provision local k3d + ArgoCD App-of-Apps.
3. **REF-*** items are addressed when the reference workload is ported in Stage 07.

> Backlog items mirror memory: significant decisions are also stored via `ruflo memory store` and in
> the `MEMORY.md` bank so future sessions recall them without re-deriving.
