# ADR-0010: K3s as the only cluster substrate, locally and on AWS

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

The platform must run identically on a developer workstation, in a staging environment, and in production on AWS. One stack per use case is a non-negotiable design principle. We will not maintain two parallel Kubernetes deployments.

K3s is a CNCF-certified Kubernetes distribution, single binary, sub-100 MB. Locally it runs in Docker via k3d. On a VM it runs via the official install script. On AWS it runs on EC2 with the same install script and cloud-init.

EKS (managed control plane on AWS) was considered. It would be a second cluster topology with different upgrade cadence, different IAM integration, different logging path, and different operational runbooks. That is the duplication we are forbidden to introduce. K3s on EC2 already gives us a Kubernetes cluster on AWS; nothing about EKS solves a problem that K3s-on-EC2 has not already solved.

## Decision

The platform uses **K3s exclusively** as the cluster substrate, in all three environments:

| Environment | Implementation | Folder |
|---|---|---|
| Local development | k3d (K3s inside Docker) | `platform/cluster/k3d-local/` |
| Staging | K3s installed via the official script on a single Linux VM | `platform/cluster/k3s-on-vm/` |
| AWS production | K3s installed via the official script on EC2 instances (Auto Scaling Group; embedded etcd; cloud-init) | `platform/cluster/k3s-on-vm/` (reused; AWS-specific cloud-init overlay) |

There is no EKS option. The `platform/cluster/eks-aws/` folder does not exist.

Across all three environments:

- Traefik (K3s default ingress) is disabled. Kong AI Gateway replaces it per ADR-0012.
- Multi-node K3s uses embedded etcd. Single-node K3s uses SQLite (local development only).
- The K3s Helm Controller is not used; ArgoCD owns reconciliation per ADR-0008.

## Consequences

Positive:

- One substrate, one upgrade story, one set of runbooks.
- Same kubeconfig shape locally and in production; same Helm charts apply identically.
- Lower cost on AWS than EKS.
- No vendor-managed dependency on a cluster control plane.

Negative:

- Operating the K3s control plane on AWS is our responsibility. The K3s install script handles this and is well-documented; the operational burden is small but real.
- We do not benefit from EKS-managed control-plane upgrades. We pin K3s versions and upgrade on a documented cadence.
- Some K8s features that EKS provides by default (Pod Security Standards enforcement, certain storage classes) need explicit configuration on K3s. We do that work once in `platform/cluster/k3s-on-vm/` and reuse.

Neutral:

- For teams that prefer a managed control plane, the only path is to fork the repository and add an EKS variant. The platform itself does not include one.

## Alternatives considered

- **EKS as a parallel option**: rejected for duplicate-stack reasons. Two AWS deployments for the same use case violates the single-stack rule.
- **EKS only**: rejected because local development still needs a K8s cluster, and we want one substrate across environments.
- **kind for local + K3s for production**: rejected because kind is designed for testing, not production-equivalent local development.
- **kubeadm-managed cluster**: rejected because operational overhead is higher than K3s with no observable benefit.

## References

- K3s CNCF project page: https://www.cncf.io/projects/k3s/
- K3s install documentation: https://docs.k3s.io/
- K3s embedded etcd HA: https://docs.k3s.io/datastore/ha-embedded
- k3d documentation: https://k3d.io/
- ArgoCD on K3s install guide (February 2026): https://oneuptime.com/blog/post/2026-02-26-install-argocd-k3s/view
