# ADR-0009: Register RuntimeClass "cube" for sandboxed pod execution

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

ADR-0005 selected CubeSandbox for tool execution and noted that CubeShim implements the containerd Shim v2 interface. This makes a second integration model available: instead of (or in addition to) calling CubeMaster's E2B-compatible REST API from `mcp-sandbox-runner`, we can schedule a pod with `runtimeClassName: cube` and Kubernetes will run that pod inside CubeSandbox directly.

The two integration models differ in what they sandbox:

- **REST API via E2B SDK**: sandboxes a single tool invocation. The sandbox lives only for the duration of the call. Good fit for the typical MCP tool-call latency budget.
- **RuntimeClass cube**: sandboxes an entire pod. The sandbox lives for the lifetime of the pod. Good fit for long-running per-workload sandboxing (e.g., an agent worker that should be entirely confined).

We need both options, because different workloads have different risk profiles.

Kubernetes RuntimeClass is a stable API (since v1.20). Registering one is a single CRD plus a `RuntimeClass` resource pointing at the handler name configured in containerd.

## Decision

Register `RuntimeClass cube` in every K3s cluster the platform provisions, with handler `cube` pointing at the CubeShim binary installed on each node that participates in the Cube pool. The RuntimeClass definition lives at `platform/runtime-classes/cube.yaml` and is reconciled by ArgoCD.

A `nodeSelector` constraint tags Cube-capable nodes (`runtime=cube`) so that pods using `runtimeClassName: cube` only schedule onto KVM-enabled hosts.

The default runtime stays `runc`. Only pods that explicitly request `runtimeClassName: cube` use the Cube runtime. OPA Gatekeeper enforces that pods in the tools namespace must use `runtimeClassName: cube`.

## Consequences

Positive:

- Two integration models for two use cases. Tool invocations go via the runner; long-lived sandboxed workloads schedule directly.
- Standard Kubernetes mechanism; no platform-specific scheduler glue.
- OPA Gatekeeper enforces the constraint at admission, not at runtime.

Negative:

- Operating two runtimes on the same cluster requires understanding which pods use which. Documentation in `platform/runtime-classes/README.md` mitigates.
- Cube nodes must be KVM-capable. Mixed clusters with non-KVM nodes need careful nodeSelector configuration.

Neutral:

- The CubeShim binary install is part of the node bootstrap pipeline (Stage 01 / Stage 09).

## Alternatives considered

- **Only the REST/E2B integration**: rejected because some workloads benefit from full-pod sandboxing (long-lived agent workers handling untrusted input).
- **Only the RuntimeClass integration**: rejected because per-tool-call sandboxing via short-lived pods is operationally heavier than the E2B-style API call to a sandbox-as-a-service.
- **Kata Containers RuntimeClass**: rejected per ADR-0005.

## References

- Kubernetes RuntimeClass docs: https://kubernetes.io/docs/concepts/containers/runtime-class/
- CubeShim containerd Shim v2 architecture: https://github.com/TencentCloud/CubeSandbox/blob/master/docs/architecture/overview.md
