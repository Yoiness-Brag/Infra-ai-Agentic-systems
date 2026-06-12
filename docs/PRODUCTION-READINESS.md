# Production-Readiness Audit - infra-code MVP

Staff-grade audit of the kagent-on-K3s Gemini agent MVP, produced by a 12-dimension parallel review
(security, database, data-pipelines, backend, tools, kagent-runtime, gateway, containers, ci-cd-gitops,
supply-chain, agentops-observability, eval). Every finding was validated against current vendor docs and
2025-2026 engineering sources via context7 and web search. Findings are classed DEFECT (violates the
contract, breaks at runtime, or fails a documented intent) or DEFERRED (an accepted MVP scope reduction).

Reference contract: `infra-code/SPEC.md`. Parent platform: `../../.backlog/build-understanding.md`,
`../../.backlog/k8s-requirements.md`, `../../docs/adr/`.

## 1. Executive summary

The application layer is strong: fail-closed config, hardened pod securityContexts, JWT alg-pinning,
bounded asyncpg pools, idempotent session upsert, and disciplined Dockerfiles for agent-backend. The
weaknesses concentrate at the network/control plane and the supply chain. As committed, the MVP has
defects that prevent it from serving a request or running the agent loop, and the GitOps `mvp-up` path
cannot stand up the cluster. None of these are large; all are enumerated below with file references.

Verdict: solid MVP engineering, NOT yet runnable as committed. Fixing the seven P0/P1 connectivity and
config defects in section 3 makes it functional; the remaining items are tracked deferrals.

## 2. Readiness scorecard (per dimension)

| Dimension | Grade | Headline |
|---|---|---|
| Security and auth | C+ | App-layer auth and pod hardening are excellent; two P0 NetworkPolicy defects break all traffic; no OPA, no TLS, plain Secrets |
| Database | B- | Fail-closed creds, bounded pool, idempotent upsert solid; FalkorDB has no persistence configured (contradicts ADR-0004); cross-subject session takeover |
| Data pipelines / memory | B- | group_id partitioning and failure-isolation correct; backend Graphiti ops unbounded (contradicts SPEC); no idempotency key on episode writes |
| Backend (FastAPI) | B+ | Async-correct, resilient A2A edge, fail-closed; SSE is a single-shot envelope; Graphiti edge has no timeout/breaker |
| Tools (MCP) | B- | Correct SDK config and hardening; no endpoint auth, no sandbox, zero prompt-injection handling on tool results |
| kagent runtime | B+ | v1alpha2 manifests correct, A2A URL verified end-to-end; no controller HA, no per-call cost ceiling, kagent emits no telemetry as configured |
| Gateway (Kong) | C | Topology and securityContext good; the `${{ env }}` secret interpolation does not work in DB-less Kong (gateway non-functional as written); no TLS, no AI guardrails |
| Containers / images | B | agent-backend production-grade; both MCP images crash under read-only rootfs (no writable /tmp); graphiti single-stage ships build-essential; no lockfiles |
| CI/CD and GitOps | B- | CI gate and App-of-Apps skeleton staff-grade; `mvp-up` GitOps path cannot install kagent/Kong Helm releases; no Rollouts/Image-Updater |
| Supply chain | C+ | Blocking Trivy gate good; no action is SHA-pinned (the very incident SPEC cites is unmitigated); no lockfiles, SBOM, signing, secret-scan, SAST |
| AgentOps / observability | C+ | RED metrics, structured logs, scrape topology solid; no distributed tracing, no LLM token/cost telemetry, 0% gen_ai semconv, no alerting |
| Eval / quality gates | C | Clean runner with pinned determinism; not wired into CI, n=8 is statistically inadequate, no regression detection, single same-family judge |

## 3. MUST-FIX defect register (blocks the MVP or violates the contract)

P0 items prevent the system from running. P1 items break a documented intent or a real runtime path.

| ID | Sev | Dimension | File | Defect | Fix |
|---|---|---|---|---|---|
| D-01 | P0 | security | `platform/foundation/network-policies.yaml`, `platform/kagent/` | kagent namespace is default-deny ingress+egress with zero allow-edges; the A2A call (backend->8083), kagent->MCP (3001/3002), kagent->Kong (Gemini), and kagent->kube-apiserver are all blocked. The agent loop cannot run. | Add `platform/kagent/networkpolicy.yaml` granting those ingress/egress edges + DNS + apiserver |
| D-02 | P0 | security | `platform/kong/k8s/networkpolicy.yaml`, `services/*/k8s/deployment.yaml` | NetworkPolicy label mismatch: Kong egress selects `app: agent-backend` but the pod is labeled `app.kubernetes.io/name`; backend egress to MCP selects `app.kubernetes.io/name` but MCP pods are `app:`. Selectors resolve to nothing under default-deny, so Kong cannot reach the backend and the backend cannot reach the MCPs. | Standardize to dual labels (`app` and `app.kubernetes.io/name`) on all workload pods, or align selectors |
| D-03 | P0 | gateway | `platform/kong/kong.yaml`, `platform/kong/k8s/kong-config-configmap.yaml` | Kong DB-less does NOT expand `${{ env "JWT_SECRET" }}` / `${{ env "GOOGLE_API_KEY" }}` (that is a decK render-time feature). Kong loads the literal strings, so no JWT validates and the Gemini key is sent literally. Gateway non-functional. | Use the Kong env-vault form `{vault://env/JWT_SECRET}` / `{vault://env/GOOGLE_API_KEY}` (already documented in the README, not applied), or an envsubst initContainer |
| D-04 | P0 | ci-cd | `platform/argocd/applications/`, `platform/{kagent,kong}/helmfile.yaml` | kagent and Kong are Helm releases installed only by `mvp-up-direct`; no ArgoCD Application installs them. Under `make mvp-up`, ArgoCD applies kagent CRs with no controller and Kong routes with no Kong -> waves 2-4 never go Healthy. `mvp-up` and `mvp-up-direct` are not equivalent. | Add ArgoCD Helm-source Applications for kagent (wave 2) and Kong (wave 1); AppProject already whitelists both registries |
| D-05 | P1 | containers | `services/mcp-web-search/k8s/deployment.yaml`, `services/mcp-graphiti-memory/k8s/deployment.yaml` | Both set `readOnlyRootFilesystem: true` with no writable `/tmp` or `$HOME`; `google-genai`/graphiti write caches to `$HOME/.cache` and `/tmp` on first call. TCP probe passes, then the first real tool call fails with read-only-fs. | Add `emptyDir` mounts for `/tmp` and a writable HOME (mirror agent-backend) |
| D-06 | P1 | backend, data | `services/agent-backend/app/memory.py` | Backend Graphiti `add_episode`/`search`/`build_indices` have no `asyncio.wait_for` and no breaker, directly contradicting SPEC 16/17. A stalled Gemini/FalkorDB call hangs the request worker with no exception for the `/chat` handler to catch. | Wrap all three calls in `asyncio.wait_for(timeout=...)`; add the timeout to config; serialize init with a lock |
| D-07 | P1 | gateway, ci-cd, supply-chain | `.github/workflows/ci.yaml` | No `uses:` is SHA-pinned. SPEC 17 cites the March-2026 trivy-action tag-hijack but pins to a mutable tag `@0.36.0` - the same reference class that was hijacked. checkout/buildx/build-push/setup-helm/setup-python are all floating tags. | Pin every action to a 40-char commit SHA with a `# vX.Y.Z` comment; add Renovate for SHA bumps |
| D-08 | P1 | database | `platform/data/falkordb.yaml` | No persistence configured (`--appendonly`/`--save` absent); FalkorDB falls back to Redis default save points which images often ship disabled. Session memory can be lost on restart despite the PVC. Contradicts ADR-0004 ("we configure both RDB and AOF") and the README durability claim. | Add `--appendonly yes --appendfsync everysec` and explicit `--save` points |
| D-09 | P1 | database | `platform/data/postgres.yaml`, `services/agent-backend/app/sessions.py` | Session upsert keys on `session_id` alone and never guards `subject` on conflict; a client supplying a known `session_id` under a different JWT subject takes over another subject's row. Not waived by SPEC 15 (which only waives the JWT issuer model). | Guard `ON CONFLICT ... WHERE sessions.subject = EXCLUDED.subject` and treat 0 rows as 403, or key on `(app, subject, session_id)` |
| D-10 | P2 | containers, supply-chain | `services/mcp-graphiti-memory/Dockerfile` | Single-stage build ships `build-essential` (gcc/make) into the runtime image, enlarging size and CVE surface and putting a compiler in the sandboxed tool pod. | Convert to the 2-stage uv pattern agent-backend already uses |
| D-11 | P2 | backend, supply-chain | `services/agent-backend/pyproject.toml` | `graphiti-core>=0.9` contradicts SPEC 16 and the MCP service `>=0.13`; risks resolving an API-incompatible release across two clients sharing one graph. | Bump to `>=0.13` |
| D-12 | P2 | security | `platform/kong/values.yaml` | Kong securityContext omits `seccompProfile: RuntimeDefault` (every other workload sets it). | Add it |
| D-13 | P2 | tools | `services/mcp-graphiti-memory/README.md` | README still documents the embedding model as `embedding-001`; code and SPEC 17 use `gemini-embedding-001`. Stale doc. | Update the README |
| D-14 | P2 | eval, observability, gateway | `infra-code/SPEC.md` 13, 15, 16 | Doc inaccuracies: SPEC 13 claims the eval is a CI job (no eval job exists in `ci.yaml`) and "2 of the 5 platform metrics" (correctness is not one of the platform five); SPEC 15's deviation ledger omits TLS-off, plain-Secrets, FalkorDB no-auth, Grafana anonymous, OTel tracing, Loki, gen_ai semconv, Argo Rollouts, Image Updater, the four-tool harness, RAGAS, red-team eval, MCP no-auth/no-sandbox, and imperative secrets. | Correct the wording and complete the deviation ledger (done in this pass - see SPEC 18) |

## 4. DEFERRED register (accepted MVP scope reductions - track, do not silently drop)

These are legitimate for a prototype but several are not yet recorded in SPEC 15. They become mandatory at
the platform stages noted.

- HA everywhere: single-replica Postgres/FalkorDB/Kong/kagent-controller; no CNPG, no leader election (Stage 02/06/14).
- No backups/PITR for Postgres or FalkorDB (Stage 02).
- No schema migration tooling (Alembic/Atlas); DDL via init ConfigMap + idempotent CREATE (Stage 07+).
- No NATS async ingestion, no DLQ, no UUIDv7 idempotency key + Redis dedup on memory writes (Stage 08).
- No CubeSandbox / `runtimeClassName: cube`; MCP tools run as plain pods (defensible only because no tool runs untrusted code - do not copy the pattern for a `code-exec` tool) (Stage 09).
- No OPA Gatekeeper / policy-as-code; pod hardening is convention, not admission-enforced (Stage 11).
- Kong OSS: no `ai-proxy-advanced`, no token-aware AI rate limiting, no `ai-semantic-cache`, no `ai-prompt-guard` (no perimeter prompt-injection/PII defense) (Enterprise/Konnect or self-hosted guard).
- No TLS/cert-manager; cleartext Bearer token at the k3d edge; no mTLS (Stage 03/14).
- Plain K8s Secrets; no encryption-at-rest, no External Secrets/Vault/SOPS/Sealed-Secrets; secrets are imperative (`make secrets`), outside GitOps reconciliation (Stage 14).
- Observability: no distributed tracing/OTel, no gen_ai.* semconv, no Langfuse LLM/token/cost telemetry, no Loki, no Mimir Ruler alerting, no SLOs, ephemeral Prometheus (Stage 03/12).
- Supply chain: no SBOM, no cosign/SLSA signing, no secret-scanning, no SAST, no dependency lockfiles, base images tag-pinned not digest-pinned (Stage 13).
- Eval: no four-tool harness (DeepEval/Promptfoo/Ragas/Inspect AI), no RAGAS gates, no red-team/injection eval, no online in-prod scoring, no regression detection, n=8 golden set (Stage 12).
- CI/CD: no Argo Rollouts canary, no ArgoCD Image Updater, image-tag rule `^[a-f0-9]{7}$` not exercised (Stage 13).

## 5. Cross-cutting themes

- Prompt-injection / tool-poisoning is unhandled end to end: `web_search` returns attacker-controlled web
  content straight into agent context, `memory_search` returns prior-turn content, Kong has no `ai-prompt-guard`,
  and there is no eval probe for it. This is the largest unaddressed security theme (OWASP LLM-01) and is not
  disclosed anywhere. Mitigate cheaply (delimit/length-cap/strip tool results) and track for `eval-svc` red-team.
- Idempotency is absent on every memory write (no episode uuid, no dedup table), so the platform's at-least-once
  + UUIDv7 invariant is not forward-compatible; this bites the moment NATS async ingestion or any `/chat` retry lands.
- Observability of the agent loop itself (the multi-hop reason->tool->memory path) is the biggest blind spot:
  one A2A counter conflates kagent + both tools + Gemini, and no trace context crosses the A2A boundary.
- Doc honesty: SPEC 15's deviation ledger is materially incomplete; multiple agents independently flagged that a
  reader would assume capabilities (tracing, gen_ai spans, CI eval gate) that are absent. Section SPEC 18 closes this.

## 6. Recommended remediation order

1. Make it run: D-01, D-02, D-03, D-04 (connectivity + gateway secrets + GitOps Helm apps).
2. Make it not crash / not hang: D-05, D-06.
3. Make it honest: D-14 (SPEC ledger + wording) - done in this pass.
4. Make it durable/correct: D-08, D-09, D-11.
5. Harden supply chain: D-07 (SHA-pin), D-10, lockfiles, SBOM.
6. Then the staged platform deferrals (section 4) in stage order.
