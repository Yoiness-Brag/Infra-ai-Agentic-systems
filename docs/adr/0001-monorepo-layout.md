# ADR-0001: Monorepo layout for platform and reference workload

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

The platform consists of approximately a dozen services and a dozen infrastructure components, plus shared schemas, documentation, and CI configuration. We considered two repository topologies: (a) a single monorepo containing platform-as-code, services, shared schemas, and docs; (b) a multi-repo split into one repo per service plus one platform-config repo.

The forces in play:

- The platform and the reference workload are co-evolving. A change to a NATS subject contract typically requires synchronized changes in `agent-orchestrator`, `agent-worker`, and the AsyncAPI schema. A monorepo makes that one PR; a multi-repo makes it three coordinated PRs.
- Documentation discipline (per-folder README, FLOW.mmd, runbook.md) is easier to enforce in CI when all folders live in one repo.
- We have one ArgoCD App-of-Apps targeting `platform/argocd/applications/`. ArgoCD treats path-scoped Applications as the same repo regardless of monorepo or multi-repo, but the manifest write-back from CI is simpler with a single repo.
- A team of one or two people is faster on a monorepo than on a polyrepo at this stage.

## Decision

We will use a single monorepo at `Infra-ai-Agentic-systems/` with the layout described in `README.md`. Code, platform manifests, schemas, and documentation live together. CI builds only the services whose paths changed in a given commit.

We will not split the GitOps target into a separate repo. Instead, the CD workflow writes image-tag bumps to `platform/argocd/applications/*` on the same branch; ArgoCD reconciles from that path.

## Consequences

Positive:

- Single source of truth. A `git log` traces a feature across services, schemas, and manifests in one place.
- Atomic cross-cutting changes. Schema bump and consumer update land in one PR.
- Easier documentation enforcement.

Negative:

- The repo will get large. We mitigate by running CI only on changed paths and by keeping uv lockfiles per service rather than one shared lockfile.
- A single repo loses the natural boundary that separate repos provide for permission scoping. We mitigate with CODEOWNERS once team size grows.
- Cloning is heavier for someone who only wants to look at one service.

Neutral:

- ArgoCD performance under a monorepo is well-documented; we follow the Hypatos pattern of path-scoped Applications grouped by cluster and project.

## Alternatives considered

- **Multi-repo**: one repo per service plus a platform-config repo. Rejected because at our team size and given the co-evolution rate of services and schemas, the coordination cost outweighs the boundary benefit.
- **Hybrid (services monorepo + separate platform repo)**: rejected because the platform manifests reference image tags built from the services repo, and we want the image-tag write-back to be a path-scoped change in the same repo rather than a cross-repo PR dance.

## References

- Hypatos, "Optimizing ArgoCD for Monorepo setup": https://medium.com/@michail.gebka/optimizing-argocd-for-monorepo-setup-7c5f548e5575
- GitOps best practices 2026: https://devopstales.com/tools-and-technologies/gitops-best-practices-2026/
