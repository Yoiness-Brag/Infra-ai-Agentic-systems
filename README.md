# infra-code — kagent-on-K3s agent MVP

A working, production-grade **MVP prototype**: a Gemini-powered agent running on a **kagent** runtime on
**k3d/K3s**, fronted by **Kong** (JWT + Gemini egress), with **2 MCP tools** (web-search +
graphiti-memory), **session memory** in **Graphiti-on-FalkorDB**, **session IDs** in **Postgres**,
**Prometheus+Grafana** observability, a **simple eval**, and **ArgoCD** GitOps + CI.

> **Read [`SPEC.md`](SPEC.md) first** — it is the build contract (namespaces, DNS, ports, secrets, auth).
> This is a deliberate MVP slice of the full platform; deviations from the ADRs are listed in SPEC §15.

## Run it locally (kagent-based, the supported path)

The local path is `make mvp-up-direct`: it creates a k3d cluster, builds and imports the 3 service
images, creates the K8s Secrets from your `.env`, applies every layer in wave order, installs the
kagent control plane and the Kong proxy via Helm, applies the kagent NetworkPolicy, and renders the
Kong declarative config. Run from the `infra-code/` directory.

### 1. Prerequisites

Install and have on PATH: `docker`, `k3d`, `kubectl`, `helm`, `helmfile`, and `envsubst` (the
`gettext` package). You also need a **Google Gemini API key** (https://aistudio.google.com/apikey).

```bash
docker --version && k3d version && kubectl version --client \
  && helm version && helmfile --version && envsubst --version
```

### 2. Set the one required secret

`.env/.env.infra` is already populated with local dev values for `JWT_SECRET`, `POSTGRES_PASSWORD`,
and `FALKORDB_PASSWORD`. The only blank is your Gemini key. Edit the file and set it:

```
GOOGLE_API_KEY=AIza...your-key...
```

(`.env/` is gitignored, so this never gets committed. `make` refuses to start if the key is empty.)

### 3. Bring up the cluster

```bash
cd infra-code
make mvp-up-direct
```

### 4. Wait for the core deployments to be Ready

```bash
kubectl get pods -A                                            # watch until all are Running/Ready
# stores are StatefulSets:
kubectl -n ai-platform rollout status statefulset/postgres
kubectl -n ai-platform rollout status statefulset/falkordb
# in-repo services are Deployments:
kubectl -n ai-platform rollout status deploy/mcp-web-search
kubectl -n ai-platform rollout status deploy/mcp-graphiti-memory
kubectl -n ai-platform rollout status deploy/agent-backend
# control plane + gateway are Helm-named (confirm the actual names if these differ):
kubectl -n kagent     get deploy   # then: kubectl -n kagent rollout status deploy/<kagent-controller-deploy>
kubectl -n ai-gateway get deploy   # then: kubectl -n ai-gateway rollout status deploy/<kong-deploy>
```

### 5. Smoke-test the full chain and run the eval

```bash
make smoke    # mints a JWT, POSTs /chat through Kong at localhost:8080, prints the SSE answer
make eval     # runs the golden-set Gemini LLM-as-judge over /chat
```

`make smoke` exercises the whole path: Kong (JWT) -> agent-backend (auth, Postgres session,
Graphiti/FalkorDB memory) -> A2A -> kagent Agent (Gemini + the 2 MCP tools) -> SSE response.

### 6. Tear down

```bash
make mvp-down   # deletes the k3d cluster
```

### Useful targets

```bash
make help       # list all targets
make token      # mint a short-lived HS256 JWT (iss=mvp-app)
make secrets    # (re)create the K8s Secrets from .env
make lint       # ruff + kustomize build + kubeconform (best-effort)
```

### Notes and caveats

- **Use `make mvp-up-direct` locally.** `make mvp-up` is the GitOps path (ArgoCD App-of-Apps) and
  additionally needs this repo pushed to a remote the in-cluster ArgoCD can reach, plus Helm
  Applications for kagent/Kong (see SPEC §19). `mvp-up-direct` has no git or remote dependency.
- **Pin the kagent chart before a clean run.** The helmfile floor is a placeholder `0.6.21`; resolve
  the real published patch with `helm show chart oci://ghcr.io/kagent-dev/kagent/helm/kagent` and set
  `CHART_VERSION` (and `KONG_CHART_VERSION` if needed).
- **Deviations from the full platform** (Prometheus instead of Alloy/LGTM-P, OSS Kong plugins, no
  CubeSandbox/OPA/HA, etc.) are tracked in [`SPEC.md`](SPEC.md) §15-19.
- **Production-readiness audit** (what is and is not staff-grade, with remediation) is in
  [`docs/PRODUCTION-READINESS.md`](docs/PRODUCTION-READINESS.md).

### Troubleshooting

```bash
kubectl get pods -A                       # find non-Ready pods
kubectl -n <ns> logs deploy/<name>        # read a failing pod's logs
kubectl -n <ns> describe pod <pod>        # events: image pull, secret missing, scheduling
```

- `401` on `make smoke`: the Kong `kong-declarative` ConfigMap must carry the real `JWT_SECRET`
  (rendered by `envsubst` during `mvp-up-direct` — confirm `envsubst` is installed).
- `mcp-graphiti-memory` CrashLoopBackOff: it fails closed if `GOOGLE_API_KEY` is empty — set it, then
  `make secrets` and restart the deploy.
- Kong not reachable at `localhost:8080`: confirm `deploy/kong-kong` is Ready and the k3d
  loadbalancer mapped host port 8080 (`k3d cluster list`).

## Layout

```
infra-code/
  SPEC.md                     build contract (source of truth)
  docs/PRODUCTION-READINESS.md staff-grade audit + remediation register
  Makefile                    mvp-up-direct/down, build-images, secrets, token, smoke, eval
  .env/.env.infra             all infra variables (gitignored; set GOOGLE_API_KEY)
  cluster/k3d/                k3d cluster config (hostport 8080->80, Traefik off)
  platform/
    foundation/               namespaces + default-deny NetworkPolicies + secret templates
    argocd/                   App-of-Apps root + project + applications/ (GitOps path)
    kong/                     Kong OSS gateway: helmfile + values + declarative config (jwt, rate-limiting, ai-proxy, prometheus)
    data/                     FalkorDB + Postgres (+ sessions schema)
    kagent/                   kagent helmfile + ModelConfig(Gemini) + Agent + 2x RemoteMCPServer + NetworkPolicy
    observability/            Prometheus + Grafana + dashboard
  services/
    agent-backend/            FastAPI: auth, sessions, Graphiti memory, A2A -> kagent Agent
    mcp-web-search/           MCP server (STREAMABLE_HTTP, port 3001)
    mcp-graphiti-memory/      MCP server wrapping Graphiti/FalkorDB (port 3002)
  eval/                       golden set + Gemini LLM-as-judge
  .github/workflows/          CI: build 3 images, Trivy scan, helm/kustomize/kubeconform lint
```
