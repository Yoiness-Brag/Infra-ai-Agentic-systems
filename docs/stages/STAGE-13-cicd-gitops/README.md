# Stage 13 — CI/CD GitOps

## Goal

Wire up GitHub Actions for per-service CI; ArgoCD Image Updater for automated image bumps; Argo Rollouts for canary on orchestrator and worker; the full GitOps loop is in place.

## Depends on

All preceding stages.

## Deliverables

- `.github/workflows/ci-build.yaml` (per-service, path-filtered).
- `.github/workflows/ci-platform.yaml` (Helm + kustomize + schema + Mermaid lint).
- ArgoCD Image Updater config per service.
- Argo Rollouts CRDs for agent-orchestrator and agent-worker.
- Trivy scan in CI on every image.
- DeepEval gate in CI (from Stage 12).

## Non-goals

- No multi-cluster ArgoCD federation yet; Stage 14 introduces the AWS cluster.

## Acceptance criteria

1. A merged PR causes the cluster to converge to the new image within a documented SLO.
2. A canary failure stops the rollout at the analysis step.
3. `git revert` of the image-bump commit rolls back production.

## Next stage

Stage 14: replicate the local setup on AWS.
