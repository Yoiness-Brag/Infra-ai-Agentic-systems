# Stage 14 — AWS Parity

## Goal

Replicate the local k3d-based platform on AWS as K3s-on-EC2 (the only option per ADR-0010), with identical manifests. Move CubeSandbox onto KVM-capable EC2 instances. Wire up the AWS Load Balancer Controller and Route53.

## Depends on

Stage 13.

## Deliverables

- `platform/cluster/k3s-on-vm/aws/` overlay with Terraform manifests for the AWS-specific cloud-init and Auto Scaling Group definition.
- A CubeSandbox node pool on `*.metal` or KVM-enabled families.
- Cross-cluster ArgoCD configuration if multi-cluster is in scope.
- Cost guardrails: spot for workers where appropriate, savings plans for the control plane.

## Non-goals

- No specific AWS-managed-service substitutions (no DynamoDB, no S3 for memory). The platform stays self-contained.

## Acceptance criteria

1. The same Helm + ArgoCD path reconciles cleanly on AWS.
2. Latency and throughput meet the SLOs documented in each layer's README.
3. The reference workload passes its end-to-end smoke test on AWS.

## Next stage

None; the platform is in production.
