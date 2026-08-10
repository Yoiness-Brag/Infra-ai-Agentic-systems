# K8s / Infrastructure Deployment Requirements Catalog

> Extracted 2026-06-12 from the scaffold/contract READMEs via the kubernetes-deployment lens
> (container → manifests → Helm → networking → security → observability → GitOps). **Stage 00: 0
> manifests exist yet** — this is the deployment contract to build against. Pair with
> `build-understanding.md`. Contradictions are tracked separately in `doc-contradictions.md`.

## 1. Cluster substrate (ADR-0010 — K3s only, no EKS)

Platform manifests (L1/L2/L4/L6/L7) are **identical across all envs**; only network topology +
storage-class wiring differ, isolated under `platform/cluster/`.

| Aspect | k3d-local | K3s-on-VM (staging) | K3s-on-EC2 (prod) |
|---|---|---|---|
| Source | `platform/cluster/k3d-local/` | `platform/cluster/k3s-on-vm/` | `platform/cluster/k3s-on-vm/aws/` |
| Nodes | 1 server | VM / small cluster | EC2 ASG multi-node |
| HA datastore | none | embedded etcd (`--cluster-init`) | embedded etcd |
| Provision | `k3d cluster create infra-ai` via `make local-up` | get.k3s.io script (Ansible) | Terraform (VPC/SG/ASG/EBS) + cloud-init |
| Ingress | k3d LB hostports 80/443→localhost | MetalLB *(gap)* | AWS ALB/NLB *(gap)* |
| Storage | local-path-provisioner | StorageClass *(gap)* | EBS |
| Traefik | disabled (Kong replaces) | disabled | disabled |

- `make local-up` = k3d create → Helm-install ArgoCD → `kubectl apply platform/argocd/root.yaml` → wait
  App-of-Apps converge. `make local-down` = `k3d cluster delete infra-ai`.
- **RuntimeClass `cube`** (`platform/runtime-classes/`, ADR-0005/0009): handler `cube` → containerd →
  CubeShim Shim v2 (RustVMM+KVM); nodeSelector `runtime=cube` (KVM hosts only); default stays `runc`.
- **GPU pool is conditional/undocumented** — only `rerank-svc` *may* use a `runtime=gpu` nodeSelector;
  default CPU (2 vCPU/4 GB). bge-large embedding placement (CPU vs GPU) unpinned (gap; rel. DOC-08).

## 2. Namespaces (`platform/namespaces/`)

`argocd` · `cert-manager` · `gatekeeper-system` · `ai-gateway` (Kong) · `ai-platform` (NATS, KEDA*,
memory-svc, session-svc, rerank-svc, mcp-registry, mcp-sandbox-runner, a2a-adapter, Redis, Qdrant,
FalkorDB, app-Postgres) · `ai-observability` (Alloy, LGTM-P, Grafana, Langfuse, ClickHouse, MinIO,
eval-svc) · `kagent-system` · `cube-system` (CubeMaster/Cubelet/CubeProxy/CubeVS; privileged allowed
here) · `workload-<app>-<env>` (per workload). All default-deny NetworkPolicy + allow-list edges.
**Gaps:** `cnpg-system` (CNPG operator) absent from canonical list; KEDA ns inconsistent (`keda` per its
README vs `ai-platform` in namespaces doc); OPA `tools-*` target ns not in canonical list (rel. DOC-22).

## 3. CRDs

- **kagent (upstream, Stage 06 Helm):** `Agent`, `ModelConfig`, `ToolServer` — reconciled by 3-replica
  controller + leader election.
- **Platform `Agent.spec` extensions (no ADR — DOC-05):** `contextBudget`, `toolAllowlist`, `a2aSkills`,
  `maxSubtasks`(8), `maxSteps`(12), `runDeadline`(90s), `tokenBudget`(50K), `costBudgetUsd`(0.50),
  `resources.requests/limits` (required by OPA `RequireAgentResourceBounds`).
- **Operator CRDs:** ArgoCD `Application`/`AppProject`; CNPG `Cluster`; KEDA `ScaledObject`; Gatekeeper
  `ConstraintTemplate`+Constraints; cert-manager `ClusterIssuer`/`Issuer`/`Certificate`;
  `RuntimeClass cube`; Argo Rollouts CRDs (Stage 13).

## 4. Workloads to deploy

| Component | Kind | Source | HA | Storage | NS / Stage |
|---|---|---|---|---|---|
| ArgoCD (+Image Updater, Rollouts) | Operator | `argo/*` Helm | HA | — | argocd / 01,13 |
| cert-manager | Operator | `jetstack/cert-manager` (installCRDs) | default | — | cert-manager / 03 |
| OPA Gatekeeper | Admission webhook | `gatekeeper/gatekeeper` | HA | — | gatekeeper-system / 11 |
| Kong AI Gateway | Deployment | `kong/kong` | HA *(unspec)* | Postgres-backed | ai-gateway / 05 |
| NATS JetStream | StatefulSet | `nats/nats` | **R3 (replicas:3)** | 10Gi fileStore PVC | ai-platform / 04 |
| KEDA | Operator | `kedacore/keda` | default | — | keda* / 04 |
| CloudNativePG operator | Operator | `cnpg/cloudnative-pg` | default | — | cnpg-system / 02 |
| Postgres ×3 (app, langfuse, kong) | `Cluster`(StatefulSet) | CNPG | instances=3 | 50Gi; WAL→MinIO (Barman) PITR | ai-platform/ai-observability/ai-gateway / 02 |
| Qdrant | StatefulSet | `qdrant/qdrant` | replicas:3 | 100Gi | ai-platform / 02 |
| FalkorDB | StatefulSet | `falkordb` (Bitnami) | 1m+2r | 50Gi; RDB+AOF | ai-platform / 02 |
| Redis (platform) | StatefulSet | `bitnami/redis` | 1m+2r+Sentinel | 20Gi; AOF | ai-platform / 02 |
| ClickHouse | StatefulSet | `bitnami/clickhouse` | replicas:3 + Keeper | 200Gi | ai-observability / 02 |
| MinIO | StatefulSet | `bitnami/minio` | 4-replica erasure | 500Gi/replica | ai-observability / 02 |
| Grafana Alloy (collector) | StatefulSet (clustered) | `grafana/alloy` | **replicas:3** | — | ai-observability / 03 |
| Grafana Alloy (logs) | DaemonSet | `grafana/alloy` | per-node | — | ai-observability / 03 |
| Mimir | Microservices + Ruler | `grafana/mimir-distributed` | distributed | MinIO `mimir-blocks` | ai-observability / 03 |
| Loki | Distributed | `grafana/loki-distributed` | distributed | MinIO `loki-chunks` (14d) | ai-observability / 03 |
| Tempo | Distributed | `grafana/tempo-distributed` | distributed | MinIO `tempo-traces` (7d) | ai-observability / 03 |
| Pyroscope | StatefulSet | `grafana/pyroscope` | replicas:3 | 100Gi + MinIO `pyroscope-blocks` | ai-observability / 03 |
| Grafana | Deployment | **chart not scaffolded (gap, DOC-27)** | — | — | ai-observability / 03 |
| Langfuse Web/Worker | Deployment | `langfuse/langfuse` | 2 / 3 | ext PG/CH/Redis/MinIO | ai-observability / 03 |
| kagent control plane | Operator+Deploys | `kagent/kagent` | controller replicas:3 + leaderElection | etcd (CRDs) | kagent-system / 06 |
| CubeSandbox (Master/Cubelet/Proxy/VS/Shim) | DaemonSet+Deploys | in-repo `platform/cluster/*/cube-pool/` | — | — | cube-system / 09 |
| agent-orchestrator | Deployment | in-repo Helm | per-workload | Postgres checkpoints | workload-* / 07 |
| agent-worker | Deployment + ScaledObject | in-repo Helm | KEDA on NATS lag | — | workload-* / 07 |
| memory-svc / session-svc | Deployment | in-repo Helm | *(unspec)* | — | ai-platform / 08 |
| rerank-svc | Deployment | in-repo Helm (TEI + BGE baked) | independent scale | 2GB ephemeral model cache | ai-platform / 08 |
| mcp-registry / mcp-sandbox-runner | Deployment | in-repo Helm | *(unspec)* | registry reads `shared/proto/mcp/` | ai-platform / 09 |
| a2a-adapter | Deployment | in-repo Helm | *(unspec)* | — | ai-platform / 10 |
| eval-svc | Deployment + 60s cron | in-repo Helm | *(unspec)* | — | ai-observability / 12 |
| Ref tools (web-search/doc-search/code-exec) | Sandbox template images (not pods) | `tools/*/Dockerfile` | per-call microVM | ephemeral | CubeSandbox / 09 |

Key service DNS/ports: `qdrant:6334`(gRPC) · `falkordb:6379` · `redis:6379` · `postgres-app-rw:5432` ·
`rerank-svc:8080` · `nats:4222` · `alloy:4317/4318` · `langfuse-web:3000` · `clickhouse:9000` ·
`kong:8000` · `E2B_API_URL=http://cube-master.cube-system:8080`.

## 5. Networking

- **Gateway:** Kong (only north-south, ADR-0012) — HTTPS+SSE, per-app JWT, token-aware rate-limit,
  Redis semantic cache, prompt-guard/PII, multi-LLM `ai-proxy-advanced`; OTLP → `alloy.ai-observability:4317`.
- **Ingress per env:** k3d hostports done; MetalLB (VM) + AWS ALB (prod) **undocumented (gap)**.
- **Service mesh: NONE.**
- **NetworkPolicies (default-deny + allow-list):** memory-svc is the **only** client allowed to reach
  Qdrant/FalkorDB/Redis (agents never direct); `cube-system` ingress only from mcp-sandbox-runner;
  default-deny sandbox egress (CubeVS eBPF, per-call allowlist from manifest); workload ns may only
  reach Kong, memory-svc, mcp-sandbox-runner, Alloy, a2a-adapter, NATS.

## 6. Security / governance

- **OPA Gatekeeper constraints (full list):** `RequireResourceLimits`, `DisallowLatestImageTag`,
  `DisallowPrivilegedContainers` (except `cube-system`), `RequireCubeRuntimeClassInTools` (gates on
  `tools-*` ns — naming gap, DOC-22), `RequireAgentResourceBounds`, `RequireNetworkPolicy`,
  `RequireOTelInstrumentation` (warn-only).
- **cert-manager:** LE-staging ClusterIssuer now; LE-production deferred to Stage 14 (gap, DOC-09);
  per-workload Issuers for internal mTLS; ACME HTTP01 via Kong.
- **RBAC (3 layers):** Kong consumer/key per app (JWT `iss`) · K8s RBAC per ns · kagent CRD tool
  allowlist (re-checked by mcp-sandbox-runner each call). ArgoCD AppProjects bound per platform area.
- **Secrets:** K8s Secrets only (provider keys in `ai-gateway`; DB creds for all stores); no external
  secret manager (gap).
- **Image tags:** `${GITHUB_SHA::7}` (`^[a-f0-9]{7}$`), `:latest` forbidden (Gatekeeper + CI + Image Updater).

## 7. Autoscaling

- **KEDA:** single `nats-jetstream` scaler on **consumer lag** → `agent-worker` via per-workload
  `ScaledObject` (Stage 07); `MaxAckPending` 50/pod; **no CPU/memory HPA anywhere**.
- **Argo Rollouts (Stage 13):** canary per service with analysis gates; Trivy scan per image.

## 8. GitOps (`platform/argocd/`)

- **App-of-Apps:** `root.yaml` → `applications/*.yaml` (one per component/service) → paths under
  `platform/` or `services/*/k8s/`. ArgoCD itself installed imperatively (Helm) in Stage 01.
- **AppProjects** (`projects/`): per platform area; bound destinations/sourceRepos/resource whitelists.
- **Image Updater:** sidecar in `argocd`; git-commits image-tag bumps into `applications/`.
- **Sync waves:** not yet declaratively annotated (gap) — ordering currently relies on stage sequence
  `01 → (02,03,04,05) → 06 → 07 → (08–12) → 13 → 14`.

## 9. Storage / backends — replication + backup

Postgres ×3 (CNPG, instances=3, WAL→MinIO Barman, **PITR**) · Qdrant (3-replica, backup policy gap) ·
FalkorDB (1m+2r, RDB+AOF) · Redis (1m+2r+Sentinel, AOF) · ClickHouse (3-replica + Keeper, backup gap) ·
MinIO (4-replica erasure; also the WAL + LGTM blocks target) · NATS (R3, 10Gi, at-least-once + Redis
dedup). Retention: Loki 14d · Tempo 7d full/30d sampled · Pyroscope 7d · Mimir 30d/1y · ClickHouse audit 90d.

## 10. Open deployment-spec gaps (resolve before the affected stage)

1. **Grafana has no chart/folder** under `platform/L7-observability/` (only `grafana-dashboards/`) — needed Stage 03. (DOC-27)
2. **Ingress/LB for VM + AWS** unspecified (MetalLB / ALB). — Stage 01/14
3. **CPU/mem requests** unspecified for every in-repo service except rerank-svc. — Stage 07+
4. **GPU pool** undocumented (NVIDIA device-plugin, node pool); embedding placement unpinned. (DOC-08) — Stage 02/08
5. **Prod TLS issuer / ACME domain** unspecified (only LE-staging). (DOC-09) — Stage 14
6. **ArgoCD sync-wave annotations** not expressed (ordering relies on stages). — Stage 01/13
7. **StorageClass** for VM/EC2 unspecified (k3d=local-path; need EBS, etc.). — Stage 01/14
8. **`Agent.spec` extension CRD mechanism** lacks an ADR. (DOC-05) — Stage 06
9. **Helm chart versions** are placeholders for kagent/FalkorDB/Langfuse. — per stage
10. **Namespace naming inconsistencies** (`tools-*` vs `cube-system`/`workload-*`; KEDA ns; `cnpg-system`). (DOC-22) — Stage 01/11
