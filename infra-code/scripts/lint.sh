#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
note() { printf '%-46s %s\n' "$1" "$2"; }

echo "== kustomize build =="
for d in platform/foundation platform/data platform/kong/k8s platform/observability \
         services/agent-backend/k8s services/mcp-web-search/k8s services/mcp-graphiti-memory/k8s; do
  if out=$(kustomize build "$d" 2>&1); then
    note "$d" "OK ($(grep -c '^kind:' <<<"$out") objects)"
  else
    note "$d" "FAIL"; echo "$out" | head -10; fail=1
  fi
done

echo
echo "== kubeconform =="
for d in platform/foundation platform/data platform/kong/k8s platform/observability \
         services/agent-backend/k8s services/mcp-web-search/k8s services/mcp-graphiti-memory/k8s; do
  if kustomize build "$d" | kubeconform -strict -ignore-missing-schemas -summary >/tmp/kc.txt 2>&1; then
    note "$d" "$(tail -1 /tmp/kc.txt)"
  else
    note "$d" "FAIL"; cat /tmp/kc.txt | head -10; fail=1
  fi
done

echo
echo "== helm template =="
helm repo add kong https://charts.konghq.com >/dev/null 2>&1 || true
helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
if helm template kong kong/kong --version "${KONG_CHART_VERSION:-3.4.1}" -n ai-gateway \
     -f platform/kong/values.yaml >/dev/null 2>&1; then note "kong chart" "OK"; else note "kong chart" "FAIL"; fail=1; fi
if helm template kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
     --version "${KAGENT_CHART_VERSION:-0.9.12}" -n kagent \
     -f platform/kagent/values.yaml >/dev/null 2>&1; then note "kagent chart" "OK"; else note "kagent chart" "FAIL"; fail=1; fi

echo
echo "== ArgoCD Application source paths exist =="
for f in platform/argocd/applications/*.yaml platform/argocd/root.yaml; do
  while read -r p; do
    [ -z "$p" ] || [ "$p" = "null" ] && continue
    rel="${p#infra-code/}"
    if [ -e "$rel" ]; then note "$(basename "$f") -> $p" "OK"; else note "$(basename "$f") -> $p" "MISSING"; fail=1; fi
  done < <(yq -r '.spec.source.path // (.spec.sources[]?.path // "")' "$f" 2>/dev/null)
done

echo
echo "== targetRevision must not be HEAD =="
if grep -rn 'targetRevision: HEAD' platform/argocd/ >/dev/null 2>&1; then
  grep -rn 'targetRevision: HEAD' platform/argocd/; fail=1
else
  note "targetRevision" "OK (no HEAD)"
fi

echo
echo "== python =="
if command -v ruff >/dev/null 2>&1; then ruff check services eval || fail=1; else note "ruff" "not installed"; fi
for f in $(find services eval -name '*.py' -not -path '*/__pycache__/*'); do
  python3 -m py_compile "$f" || fail=1
done
note "py_compile" "OK"

echo
[ $fail -eq 0 ] && echo "LINT PASSED" || { echo "LINT FAILED"; exit 1; }
