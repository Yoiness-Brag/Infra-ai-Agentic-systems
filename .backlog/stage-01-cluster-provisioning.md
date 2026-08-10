# Stage 01 — Cluster provisioning (NEXT)

Goal: provision the K3s substrate (k3d locally) + install ArgoCD and the App-of-Apps root that drives
every later stage. Depends on Stage 00 (done). Source: `docs/stages/STAGE-01-cluster-provisioning/README.md`.
Constraint: **K3s only, no EKS** (ADR-0010); no platform components beyond ArgoCD itself yet.

### [S01-01] k3d cluster definition + Make targets
- **Status:** todo · **Priority:** P1 · **Refs:** `platform/cluster/k3d-local/`, `Makefile`
- Create `platform/cluster/k3d-local/` (k3d config: server/agent nodes, ports, local registry) and
  wire `make local-up` / `make local-down`. Must work identically on macOS + Linux (Arch dev box here).

### [S01-02] ArgoCD install + App-of-Apps root
- **Status:** todo · **Priority:** P1 · **Refs:** `platform/argocd/root.yaml`, `platform/argocd/applications/`
- Install ArgoCD into the cluster; create `root.yaml` (App-of-Apps) pointing at
  `platform/argocd/applications/`. `make local-up` should leave ArgoCD healthy.

### [S01-03] ArgoCD AppProject scoping
- **Status:** todo · **Priority:** P2 · **Refs:** `platform/argocd/projects/platform.yaml`
- AppProject `platform` scoping source repos, destinations (namespaces), and allowed resource kinds.

### [S01-04] Folder discipline for new dirs
- **Status:** todo · **Priority:** P2 · **Refs:** CI folder-discipline check
- Every new folder under `platform/cluster/` and `platform/argocd/` gets `README.md` (+ `FLOW.mmd` /
  `runbook.md` where applicable) per the repo invariant.

### Acceptance (from stage doc)
1. `make local-up` → running k3d cluster, ArgoCD healthy.
2. `kubectl get applications -n argocd` shows the root Application synced.
3. Identical behaviour on macOS and Linux.

> After Stage 01, Stages 02/03/04/05 can proceed in parallel.
