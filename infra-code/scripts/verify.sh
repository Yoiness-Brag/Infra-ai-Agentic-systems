#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

KONG_URL="${KONG_URL:-http://localhost:8080}"
ARGOCD_URL="${ARGOCD_URL:-http://localhost:8081}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
fail=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=1; }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; }

echo "== cluster =="
kubectl cluster-info >/dev/null 2>&1 && pass "apiserver reachable" || { bad "apiserver unreachable"; exit 1; }
kubectl get nodes -o jsonpath='{.items[0].status.allocatable.memory}' >/tmp/alloc 2>/dev/null \
  && pass "node allocatable memory: $(cat /tmp/alloc)" || bad "cannot read node allocatable"

echo "== workloads ready =="
check_roll() { # ns kind/name
  if kubectl -n "$1" rollout status "$2" --timeout="${3:-180s}" >/dev/null 2>&1; then pass "$1 $2"; else bad "$1 $2 not ready"; fi
}
for spec in \
  "ai-platform statefulset/postgres" \
  "ai-platform statefulset/falkordb" \
  "ai-platform statefulset/minio" \
  "ai-platform deployment/agent-backend" \
  "ai-platform deployment/mcp-web-search" \
  "ai-platform deployment/mcp-graphiti-memory" \
  "ai-gateway deployment/kong-kong" \
  "kagent deployment/kagent-controller" \
  "ai-observability deployment/prometheus" \
  "ai-observability deployment/grafana" \
  "ai-observability statefulset/loki" ; do
  set -- $spec; check_roll "$1" "$2"
done
kubectl -n ai-observability rollout status daemonset/alloy --timeout=180s >/dev/null 2>&1 \
  && pass "ai-observability daemonset/alloy" || bad "alloy not ready"

echo "== no pod in a bad state =="
bad_pods=$(kubectl get pods -A --no-headers 2>/dev/null | awk '$4 ~ /CrashLoopBackOff|Error|ImagePullBackOff|ErrImagePull|CreateContainerConfigError|OOMKilled/ {print $1"/"$2" "$4}')
if [ -z "$bad_pods" ]; then pass "no crashlooping/erroring pods"; else bad "bad pods:"; echo "$bad_pods" | sed 's/^/          /'; fi

echo "== north-south edge =="
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$KONG_URL/healthz" || echo 000)
[ "$code" = "200" ] && pass "GET $KONG_URL/healthz -> 200" || bad "GET $KONG_URL/healthz -> $code (expect 200)"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST "$KONG_URL/chat" -H 'Content-Type: application/json' -d '{"message":"x"}' || echo 000)
[ "$code" = "401" ] && pass "POST /chat without JWT -> 401 (jwt plugin active)" || bad "POST /chat without JWT -> $code (expect 401)"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$KONG_URL/docs" || echo 000)
[ "$code" = "200" ] && pass "Swagger UI at $KONG_URL/docs -> 200" || bad "Swagger UI -> $code"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$KONG_URL/openapi.json" || echo 000)
[ "$code" = "200" ] && pass "OpenAPI schema -> 200" || bad "OpenAPI schema -> $code"

echo "== observability =="
up=$(kubectl -n ai-observability exec deploy/prometheus -c prometheus -- \
       wget -qO- 'http://localhost:9090/api/v1/query?query=up' 2>/dev/null | grep -o '"value"' | wc -l)
[ "${up:-0}" -gt 0 ] && pass "prometheus has $up up-series" || bad "prometheus returned no targets"
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$GRAFANA_URL/api/health" || echo 000)
[ "$code" = "200" ] && pass "grafana $GRAFANA_URL/api/health -> 200" || bad "grafana health -> $code"
ready=$(kubectl -n ai-observability exec statefulset/loki -- wget -qO- http://localhost:3100/ready 2>/dev/null | tr -d '\n')
[ "$ready" = "ready" ] && pass "loki ready" || warn "loki says: ${ready:-<none>}"

echo "== argocd =="
if kubectl get ns argocd >/dev/null 2>&1; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$ARGOCD_URL/healthz" || echo 000)
  [ "$code" = "200" ] && pass "ArgoCD UI $ARGOCD_URL -> 200" || bad "ArgoCD UI -> $code"
  notsynced=$(kubectl -n argocd get applications.argoproj.io -o json 2>/dev/null \
    | yq -r '.items[]? | select(.status.sync.status != "Synced" or .status.health.status != "Healthy") | .metadata.name' 2>/dev/null)
  if [ -z "$notsynced" ]; then pass "all Applications Synced+Healthy"; else warn "not Synced/Healthy: $(echo $notsynced | tr '\n' ' ')"; fi
else
  warn "argocd namespace absent (up-direct path)"
fi

echo
[ $fail -eq 0 ] && echo "VERIFY PASSED" || { echo "VERIFY FAILED"; exit 1; }
