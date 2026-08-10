# kagent install — MVP (v1alpha2)

Installs the kagent control plane (CRDs + controller) into the `kagent` namespace
with **Gemini** as the default provider, then applies the MVP `ModelConfig`,
`RemoteMCPServer` ×2, and `Agent` custom resources.

> Confirmed against kagent docs (`/websites/kagent_dev`). CRD `apiVersion` is
> **`kagent.dev/v1alpha2`** (introduced in the v0.6 release line).

## Charts (OCI registry `ghcr.io/kagent-dev`)

| Chart | OCI ref | Purpose |
|---|---|---|
| `kagent-crds` | `oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds` | CRDs (kagent + kmcp subchart: RemoteMCPServer/MCPServer). **Install first.** |
| `kagent` | `oci://ghcr.io/kagent-dev/kagent/helm/kagent` | Controller + UI + API (the A2A server on port 8083). |

**Version:** pin to an exact published patch on the **v0.6** line (e.g. `0.6.21`).
Resolve the current patch before installing — the docs do not freeze a single
patch number:

```bash
helm show chart oci://ghcr.io/kagent-dev/kagent/helm/kagent | grep -E '^version|^appVersion'
export CHART_VERSION=0.6.21   # set to the value you confirmed
```

> If you move to the **v0.7** line, `kmcp` is installed by default
> (`kmcp.enabled=true`); set `kmcp.enabled=false` on upgrade if you already have
> a standalone kmcp install. Re-verify all CR shapes via context7 on any bump.

## Prerequisites

- Namespace `kagent` exists (created by the GitOps namespaces+secrets wave 0, SPEC §12).
- Secret **`gemini-api`** present in `kagent` with key **`GOOGLE_API_KEY`** (SPEC §6).
  Fail-closed: install MUST NOT proceed with an empty key.

## Install — Helm (direct)

```bash
# 1. Read the Gemini key from the gemini-api Secret (never hardcode).
export GOOGLE_API_KEY="$(kubectl -n kagent get secret gemini-api \
  -o jsonpath='{.data.GOOGLE_API_KEY}' | base64 -d)"
test -n "$GOOGLE_API_KEY" || { echo "FATAL: gemini-api/GOOGLE_API_KEY is empty"; exit 1; }

# 2. CRDs first.
helm install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
  --namespace kagent --create-namespace --version "$CHART_VERSION"

# 3. Controller — Gemini default provider, key injected from the Secret.
helm install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
  --namespace kagent --version "$CHART_VERSION" \
  -f infra-code/platform/kagent/values.yaml \
  --set providers.default=gemini \
  --set providers.gemini.apiKey="$GOOGLE_API_KEY"

# 4. Apply the MVP custom resources (order: ModelConfig + MCP servers, then Agent).
kubectl apply -f infra-code/platform/kagent/model-config.yaml
kubectl apply -f infra-code/platform/kagent/remote-mcp-web-search.yaml
kubectl apply -f infra-code/platform/kagent/remote-mcp-graphiti-memory.yaml
kubectl apply -f infra-code/platform/kagent/agent.yaml
```

## Install — helmfile (declarative alternative)

```bash
export GOOGLE_API_KEY="$(kubectl -n kagent get secret gemini-api \
  -o jsonpath='{.data.GOOGLE_API_KEY}' | base64 -d)"
export CHART_VERSION=0.6.21
helmfile -f infra-code/platform/kagent/helmfile.yaml apply
# then kubectl apply the four CR manifests as above.
```

## Verify

```bash
kubectl -n kagent get pods
kubectl -n kagent get modelconfig gemini-model-config
kubectl -n kagent get remotemcpserver
kubectl -n kagent get agent mvp-agent -o wide

# A2A agent card (in-cluster path; port-forward for a local check):
kubectl -n kagent port-forward svc/kagent-controller 8083:8083 &
curl localhost:8083/api/a2a/kagent/mvp-agent/.well-known/agent.json
```

## Notes

- The `gemini-api` Secret is the single source of truth for the model key.
  Both the chart (`providers.gemini.apiKey`, injected at install) and the
  `ModelConfig` (`apiKeySecret: gemini-api` / `apiKeySecretKey: GOOGLE_API_KEY`)
  point at it.
- Per SPEC §8, Gemini egress is intended to route through Kong `ai-proxy-advanced`.
  That routing is configured in the **gateway** layer (out of scope for this dir).
