# Kong AI Gateway (`ai-gateway` namespace)

North-south entry for the MVP. Kong validates the client JWT, rate-limits, exposes
Prometheus metrics, and provides a Gemini LLM egress route (ADR-0012). Runs **OSS Kong
Gateway 3.9 in DB-less / declarative mode** — no database, config is a single
`kong.yaml` mounted from a ConfigMap.

Conforms to `infra-code/SPEC.md` §4 (DNS/ports), §6 (secrets), §7 (auth), §8 (Gemini).

## Files

| File | Purpose |
|---|---|
| `values.yaml` | Helm values: `kong/kong` chart **v2.51.0**, image `kong:3.9`, DB-less, ingress-controller off, proxy as entry, secret env injection. |
| `kong.yaml` | Declarative config (`_format_version: "3.0"`): consumer + JWT cred, `agent-backend` `/chat` route, Gemini `/llm/gemini` route, plugins. **Source of truth.** |
| `k8s/namespace.yaml` | `ai-gateway` namespace. |
| `k8s/kong-config-configmap.yaml` | `kong-declarative` ConfigMap = an in-sync copy of `kong.yaml` (mounted into the proxy). Regenerate when `kong.yaml` changes. |
| `k8s/secrets.example.yaml` | **Template only** — documents `jwt-secret` + `gemini-api` Secret contracts. Real values via `make`/`.env`, never committed. |
| `k8s/networkpolicy.yaml` | Default-deny + allow: ingress :8000/:8100, egress to `agent-backend`, DNS, Gemini :443. |
| `k8s/kustomization.yaml` | Bundles namespace + configmap + networkpolicy (not the Helm release, not the example secrets). |

## Install

```bash
# 1. namespace + ConfigMap + NetworkPolicies
kubectl apply -k infra-code/platform/kong/k8s

# 2. real Secrets (from .env, never committed — SPEC §6)
kubectl create secret generic jwt-secret -n ai-gateway \
  --from-literal=JWT_SECRET="$JWT_SECRET" --from-literal=JWT_ISS=mvp-app
kubectl create secret generic gemini-api -n ai-gateway \
  --from-literal=GOOGLE_API_KEY="$GOOGLE_API_KEY"

# 3. Kong (Helm)
helm repo add kong https://charts.konghq.com && helm repo update
helm install kong kong/kong -n ai-gateway --version 2.51.0 \
  -f infra-code/platform/kong/values.yaml
```

Result: `kong-proxy.ai-gateway:80` (k3d hostport 80 → localhost:8080).

> **Keep `kong.yaml` and `k8s/kong-config-configmap.yaml` in sync.** Regenerate the
> ConfigMap after editing `kong.yaml`:
> ```bash
> kubectl create configmap kong-declarative -n ai-gateway \
>   --from-file=kong.yaml=infra-code/platform/kong/kong.yaml \
>   --dry-run=client -o yaml
> ```

## JWT flow (SPEC §7)

```
Client ──Authorization: Bearer <HS256 JWT, iss=mvp-app>──▶ Kong jwt plugin
   Kong: look up consumer by `iss` (key_claim_name: iss) == credential key `mvp-app`,
         verify HS256 signature with shared `JWT_SECRET`, verify `exp`.
         → missing/invalid/expired ⇒ 401 BEFORE the backend is reached.
   Kong ──▶ agent-backend.ai-platform:8000 (/chat stripped to /)
   agent-backend RE-VERIFIES the same JWT (HS256, iss=mvp-app, exp) with pyjwt —
   defense-in-depth, never trusts Kong alone. 401 on failure.
```

- The **shared secret** is the `JWT_SECRET` key in the `jwt-secret` K8s Secret, present
  in **both** `ai-gateway` (Kong) and `ai-platform` (agent-backend) so signatures match.
- Set it once at platform stand-up from `.env`; `make token` mints a short-lived test JWT with
  `iss=mvp-app` signed by the same secret.
- **Fail-closed:** if `JWT_SECRET` is empty the credential `secret` is `""` and no real
  token validates — Kong rejects, agent-backend rejects.

### How the secret reaches `kong.yaml`

`values.yaml` injects Secret keys as container env (`extraEnvVars`: `JWT_SECRET`,
`JWT_ISS`, `GOOGLE_API_KEY`). `kong.yaml` references them via the built-in env **vault**
form `{vault://env/JWT_SECRET}` / `{vault://env/GOOGLE_API_KEY}`, which Kong resolves at
load time in DB-less mode (decK-style `${{ env }}` interpolation does NOT work when Kong
loads a declarative file directly, so the vault form is used). No secret value is ever
written into these committed files.

## Plugins — OSS vs Enterprise (read this)

| Concern | Plugin used (this MVP) | Tier | Enterprise alt avoided |
|---|---|---|---|
| Auth | `jwt` | **OSS / free** | — |
| Rate limit | `rate-limiting` (`policy: local`, `limit_by: consumer`, 60/min) | **OSS / free** | `ai-rate-limiting-advanced` is **Enterprise-only** |
| LLM egress | `ai-proxy` (provider `gemini`, `gemini-2.5-flash`, API key in query) | **OSS / free** (bundled in Kong 3.6+ AI Gateway) | `ai-proxy-advanced` (multi-target/load-balance/semantic routing) is **Enterprise-only** |
| Metrics | `prometheus` | **OSS / free** | — |

**Deviation note vs SPEC §7/§8:** the SPEC mentions `ai-rate-limiting-advanced` and
`ai-proxy-advanced`. Both are **Kong Enterprise** plugins and are not available in OSS
Kong Gateway. This MVP uses the OSS equivalents `rate-limiting` and `ai-proxy`, which
deliver the same MVP behavior (per-consumer rate cap; single-upstream Gemini egress).
If/when Kong Enterprise (or Konnect) is adopted, swap to the `*-advanced` variants —
the `ai-proxy` → `ai-proxy-advanced` change is the only one needed for token-based AI
rate limiting and multi-model routing.

## Gemini egress route (SPEC §8)

`POST /llm/gemini` → `ai-proxy` plugin → Gemini `gemini-2.5-flash`, `route_type:
llm/v1/chat`. Auth = `GOOGLE_API_KEY` (from the `gemini-api` Secret) sent as the `key`
query param. Keeps all LLM traffic flowing through the gateway (ADR-0012). kagent's
`ModelConfig` points its Gemini egress at this Kong route rather than calling Google
directly.

## Risks / caveats

- **Enterprise plugins unavailable** — `ai-proxy-advanced` / `ai-rate-limiting-advanced`
  require Kong Enterprise; OSS substitutes are used (table above). No token-aware AI rate
  limiting in the MVP (request-count limiting only).
- **Secret resolution** uses the Kong env vault (`{vault://env/...}`), resolved at load
  time in DB-less mode; the Kong container must carry the matching env vars (it does, via
  `values.yaml extraEnvVars`).
- **ConfigMap drift** — `kong.yaml` and `k8s/kong-config-configmap.yaml` are two copies;
  they must be regenerated together (or wire a Kustomize/CI generator).
- **Gemini egress NetworkPolicy** is IP-CIDR based (`0.0.0.0/0` minus cluster CIDRs on
  :443) since NetworkPolicy can't match DNS names — broader than strictly Google IPs.
- **`proxy.type: ClusterIP`** relies on k3d's hostport 80 mapping; on a non-k3d cluster
  switch to `LoadBalancer`/Ingress.
