# ADR-0008: GitHub Actions for CI, ArgoCD for CD

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

The platform needs a CI/CD path that:

- Builds and tests every service on every change to its path, not on every change to the repo.
- Pushes container images to a registry with content-addressable tags.
- Updates the desired state in Git in a way ArgoCD can reconcile to the cluster.
- Supports canary deployment for risky services (`agent-orchestrator`, `agent-worker`).
- Allows `git revert` as the production rollback button.
- Works identically against a local k3d cluster and against K3s-on-EC2 (the only AWS option per ADR-0010).

GitHub Actions is the de facto CI for OSS repositories. It runs free for public projects, has matrix builds, has good Helm and kubectl actions, and integrates natively with GitHub-hosted code.

ArgoCD is CNCF Graduated since 2022. The 2026 community consensus is ArgoCD over Flux for projects that want the built-in UI, the App-of-Apps pattern, and the broad ecosystem (Image Updater, Rollouts, Notifications, ApplicationSet).

The combination — CI in GitHub Actions, CD in ArgoCD — is the dominant 2026 GitOps pattern.

## Decision

The platform's CI/CD pipeline:

1. **GitHub Actions builds and tests.** On every push:
   - `ci-build.yaml` runs per-service: ruff lint, mypy where used, pytest with coverage, Trivy container scan, push image to the registry with tag `${GITHUB_SHA::7}`. Path filters ensure only changed services rebuild.
   - `ci-platform.yaml` validates Helm charts, kustomize trees, AsyncAPI/OpenAPI schemas, and Mermaid diagram syntax.
2. **ArgoCD reconciles.** A root `Application` at `platform/argocd/root.yaml` references the App-of-Apps directory `platform/argocd/applications/`. Each Application targets a path under `platform/`.
3. **Image bump via ArgoCD Image Updater.** Configured per service to watch the registry, pick the most recent image matching the tag filter `regexp:^[a-f0-9]{7}$`, write the new tag to `platform/argocd/applications/<service>.yaml`, commit on a config branch, and let ArgoCD sync.
4. **Argo Rollouts for canary.** `agent-orchestrator` and `agent-worker` deploy as `Rollout` resources with canary steps: 20% / 5 min pause / 50% / 5 min pause / 100%, each pause gated by a Prometheus analysis template that asserts no error-rate regression on the canary pods.
5. **Rollback is `git revert`.** A revert of the image-bump commit causes ArgoCD to sync back to the previous tag.

## Consequences

Positive:

- Standard tooling. Anyone familiar with GitHub Actions + ArgoCD onboards quickly.
- Path-filtered CI keeps the pipeline fast as the repo grows.
- App-of-Apps gives a single declarative entry point for the entire platform.
- Argo Rollouts canary with Prometheus analysis prevents bad deploys from hitting 100% of traffic.
- `git revert` is the rollback story, which means rollback is auditable.

Negative:

- ArgoCD Image Updater is a CNCF-incubating-tier component (less mature than ArgoCD itself). We accept the risk because the alternative is custom CI logic to do the same thing.
- GitHub Actions costs scale with private repo minutes. If the repo goes private, we revisit.
- Argo Rollouts adds another CRD to learn. The benefit (gated canary) is worth it for the two critical services; other services use plain Deployments.

Neutral:

- Both GitHub Actions and ArgoCD have rich ecosystems; we are not picking a niche tool.

## Alternatives considered

- **Flux CD**: rejected in favor of ArgoCD because of the built-in UI, App-of-Apps maturity, and the Image Updater story.
- **Jenkins**: rejected because of operational overhead for an OSS team.
- **GitHub Actions calling kubectl directly**: rejected because it bypasses GitOps. Git stops being the source of truth, and rollback becomes an out-of-band procedure.
- **Tekton + ArgoCD**: rejected because Tekton is overkill for our build needs; GitHub Actions matrix builds suffice.

## References

- ArgoCD on K3s install guide: https://oneuptime.com/blog/post/2026-02-26-install-argocd-k3s/view
- ArgoCD + GitHub Actions integration: https://oneuptime.com/blog/post/2026-02-26-argocd-github-actions-integration/view
- ArgoCD Image Updater docs: https://argocd-image-updater.readthedocs.io/en/stable/basics/update-methods/
- GitOps best practices 2026: https://devopstales.com/tools-and-technologies/gitops-best-practices-2026/
- Argo Rollouts canary documentation.
