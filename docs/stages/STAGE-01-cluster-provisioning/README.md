# Stage 01 — Cluster Provisioning

## Goal

Provision the K3s substrate that the rest of the platform reconciles onto. Locally this is k3d; on AWS this is K3s-on-EC2 depending on the operator's choice. Install ArgoCD and the App-of-Apps root that will drive every subsequent stage.

## Depends on

Stage 00.

## Deliverables

- `platform/cluster/k3d-local/` k3d cluster definition + Make target.
- `platform/argocd/root.yaml` ArgoCD App-of-Apps root pointing at `platform/argocd/applications/`.
- `platform/argocd/projects/platform.yaml` ArgoCD AppProject scoping permissions.
- `make local-up` and `make local-down` working.

## Non-goals

- No platform components installed beyond ArgoCD itself. Those come in later stages.

## Acceptance criteria

1. `make local-up` produces a running k3d cluster with ArgoCD healthy.
2. `kubectl get applications -n argocd` shows the root Application synced.
3. The cluster works the same on macOS and Linux.

## Next stage

Stage 02, 03, 04 and 05 can proceed in parallel from here.
