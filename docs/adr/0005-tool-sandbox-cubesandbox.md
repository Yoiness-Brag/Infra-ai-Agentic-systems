# ADR-0005: CubeSandbox as the tool execution sandbox

- **Status**: Accepted
- **Date**: 2026-05-25

## Context

Tool execution is the highest-blast-radius operation an agent performs. A code-generation agent that runs its own output on the host can exfiltrate environment variables, write to disk, open outbound network connections, or escape the container. Production-grade sandboxing is non-negotiable.

The seven-layer L5 requirement: "Validation and sandboxing" as a core responsibility. The Excalidraw design explicitly calls out "MCP requires sandboxing." The user-stated constraint: CubeSandbox specifically.

CubeSandbox is Tencent Cloud's open-source agent sandbox (Apache 2.0, April 2026 release), built on RustVMM and KVM. Key properties:

- Sub-60 ms average cold start via resource-pool pre-provisioning and snapshot cloning.
- Under 5 MB per-instance memory overhead via CoW and a Rust-rebuilt trimmed runtime.
- True kernel-level isolation: each sandbox has its own Guest OS kernel.
- eBPF-enforced network policy via CubeVS.
- Drop-in compatible with the E2B SDK (set `E2B_API_URL` to the CubeMaster endpoint, no code changes).
- CubeShim implements containerd Shim v2, so CubeSandbox can register as a Kubernetes RuntimeClass.
- Published Tencent Cloud production validation: P95 90 ms, P99 137 ms at 50 concurrent requests.

Alternatives considered:

- **E2B**: closed-source managed cloud is the primary distribution; OSS self-hosting exists but is secondary. Production-grade Firecracker-based. Cost is significant at scale.
- **Daytona**: container-based with gVisor, faster startup than VMs but shared-kernel.
- **Kata Containers** as a RuntimeClass: VM-grade isolation but slower startup than CubeSandbox and not purpose-built for agent workloads.
- **gVisor** as a RuntimeClass: user-space kernel, lightest of the VM-grade options, but no GPU passthrough and weaker isolation than KVM.
- **Microsandbox**: small, self-hosted, but lower production maturity.

## Decision

We use **CubeSandbox** as the tool execution sandbox.

Deployment topology: a separate node pool of KVM-capable hosts (`*.metal` on AWS, native Linux locally) hosts the CubeSandbox cluster (CubeMaster, Cubelet, CubeProxy, CubeVS, CubeHypervisor). The K3s cluster registers `RuntimeClass cube` against the CubeShim containerd Shim v2 so that pods can be scheduled directly onto the Cube runtime.

Agent code in `services/` uses the E2B Python SDK with `E2B_API_URL` pointed at the in-cluster CubeMaster Service. This means the agent code is sandbox-vendor-agnostic; we can swap to E2B managed cloud at any time by changing one environment variable.

## Consequences

Positive:

- Sub-60 ms cold start unlocks high-density tool-calling workloads without the user-visible latency tax of traditional VM startup.
- KVM-grade isolation provides containment against agent-generated malicious code at the hardware level.
- E2B SDK compatibility means our agent code does not lock us into CubeSandbox.
- Apache 2.0 license, active Tencent Cloud maintenance, production-validated at scale.
- The containerd Shim v2 integration gives us a second integration model: schedule a pod with `runtimeClassName: cube` and it runs in CubeSandbox directly, useful for long-running workload sandboxing as opposed to per-call tool execution.

Negative:

- Requires KVM-capable hosts. On AWS that means metal instances or KVM-enabled families, which cost more than standard nodes. Locally that means Linux on bare metal, WSL2 with nested virt, or a Linux VM with KVM passthrough.
- We take on a second cluster-like system to operate (CubeMaster, Cubelet pool). Operational burden is non-trivial.
- The Cube ecosystem is younger than Firecracker; there is less third-party tooling.

Neutral:

- One-click install script ships with the upstream repo. We adapt it into our `platform/cluster/` provisioning.

## Alternatives considered

- **E2B managed cloud**: rejected because we want self-hosting for cost and data sovereignty. The E2B SDK compatibility means we can switch to managed E2B without code changes if we change our mind.
- **Self-hosted E2B (Firecracker)**: rejected only because CubeSandbox offers better cold-start performance and lower memory overhead at the same isolation level, with the same SDK surface.
- **Kata Containers RuntimeClass**: rejected because cold start is ~1–2 seconds, an order of magnitude slower than CubeSandbox.
- **gVisor RuntimeClass**: rejected because user-space kernel isolation is weaker than KVM, and the use case explicitly includes potentially malicious agent-generated code.

## References

- TencentCloud/CubeSandbox: https://github.com/TencentCloud/CubeSandbox
- Architecture overview: https://github.com/TencentCloud/CubeSandbox/blob/master/docs/architecture/overview.md
- aitoolnet review: https://www.aitoolnet.com/cube-sandbox
- Sandbox comparison 2026: https://fast.io/resources/best-code-execution-sandboxes-ai-agents/
- Daytona vs E2B: https://northflank.com/blog/daytona-vs-e2b-ai-code-execution-sandboxes
