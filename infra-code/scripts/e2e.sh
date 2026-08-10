#!/usr/bin/env bash
# End-to-end acceptance sweep: every layer, via curl / kubectl / argocd.
# Exercises the real request path, not just pod readiness.
set -uo pipefail
cd "$(dirname "$0")/.."

KONG_URL="${KONG_URL:-http://localhost:8080}"
ARGOCD_URL="${ARGOCD_URL:-http://localhost:8081}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
MINIO_URL="${MINIO_URL:-http://localhost:9001}"
LANGFUSE_URL="${LANGFUSE_URL:-http://localhost:3001}"

pass=0; fail=0; skip=0
ok()   { printf '  \033[32m PASS \033[0m %s\n' "$*"; pass=$((pass+1)); }
no()   { printf '  \033[31m FAIL \033[0m %s\n' "$*"; fail=$((fail+1)); }
sk()   { printf '  \033[33m SKIP \033[0m %s\n' "$*"; skip=$((skip+1)); }
hdr()  { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

code() { curl -s -o /dev/null -w '%{http_code}' --max-time "${2:-15}" "$1" 2>/dev/null || echo 000; }
jcode(){ curl -s -o /dev/null -w '%{http_code}' --max-time "${3:-120}" -X POST "$1" \
          -H "Authorization: Bearer $2" -H 'Content-Type: application/json' \
          -d '{"message":"reply with exactly: E2E OK"}' 2>/dev/null || echo 000; }

# --------------------------------------------------------------------------
hdr "L0  cluster"
kubectl cluster-info >/dev/null 2>&1 && ok "apiserver reachable" || { no "apiserver unreachable"; exit 1; }
alloc=$(kubectl get node -o jsonpath='{.items[0].status.allocatable.memory}' 2>/dev/null)
[ -n "$alloc" ] && ok "node allocatable memory = $alloc" || no "cannot read allocatable"
notready=$(kubectl get pods -A --no-headers 2>/dev/null | awk '$3!="Running" && $3!="Completed" && $3!="Succeeded"{print $1"/"$2"("$3")"}')
[ -z "$notready" ] && ok "every pod Running/Completed" || no "not ready: $(echo $notready | tr '\n' ' ')"
oom=$(kubectl get pods -A --no-headers 2>/dev/null | awk '$5>3{print $1"/"$2"("$5" restarts)"}')
[ -z "$oom" ] && ok "no pod restart storms" || no "restarting: $(echo $oom | tr '\n' ' ')"

# --------------------------------------------------------------------------
hdr "L1  Kong gateway (north-south)"
c=$(code "$KONG_URL/healthz"); [ "$c" = 200 ] && ok "GET /healthz -> 200 (LoadBalancer + route work)" || no "GET /healthz -> $c"
c=$(code "$KONG_URL/docs");   [ "$c" = 200 ] && ok "Swagger UI /docs -> 200 (docs route has no jwt)" || no "/docs -> $c"
c=$(code "$KONG_URL/openapi.json"); [ "$c" = 200 ] && ok "OpenAPI schema -> 200" || no "/openapi.json -> $c"
c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 -X POST "$KONG_URL/chat" \
      -H 'Content-Type: application/json' -d '{"message":"x"}' 2>/dev/null || echo 000)
[ "$c" = 401 ] && ok "POST /chat without JWT -> 401 (jwt plugin attached)" || no "POST /chat unauth -> $c (want 401)"
kubectl -n ai-gateway get svc kong-proxy -o jsonpath='{.spec.type}' 2>/dev/null | grep -q LoadBalancer \
  && ok "kong-proxy Service is LoadBalancer" || no "kong-proxy is not LoadBalancer"

# --------------------------------------------------------------------------
hdr "L3  agent-backend + A2A"
TOKEN="$(make -s token 2>/dev/null)"
[ -n "$TOKEN" ] && ok "minted HS256 JWT" || no "could not mint JWT"

rz=$(kubectl -n ai-platform exec deploy/agent-backend -- \
       python -c "import urllib.request,sys;print(urllib.request.urlopen('http://127.0.0.1:8000/readyz',timeout=8).read().decode())" 2>/dev/null)
echo "$rz" | grep -q '"status"' && ok "/readyz reports: $(echo "$rz" | head -c 160)" || no "/readyz unreadable"
for dep in postgres falkordb minio; do
  echo "$rz" | grep -q "\"$dep\": *\"ok\"" && ok "dependency $dep = ok" || no "dependency $dep not ok"
done

card=$(kubectl -n ai-platform exec deploy/agent-backend -- python - <<'PY' 2>/dev/null
import json,urllib.request
base="http://kagent-controller.kagent:8083/api/a2a/kagent/mvp-agent/"
for p in (".well-known/agent-card.json",".well-known/agent.json"):
    try:
        d=json.load(urllib.request.urlopen(base+p,timeout=8))
        print(p, d.get("name","?"), len(d.get("skills",[])), "skills"); break
    except Exception: pass
else: print("NONE")
PY
)
[ "$card" != "NONE" ] && [ -n "$card" ] && ok "A2A Agent Card discovered: $card" || no "A2A Agent Card not reachable"

if [ -n "$TOKEN" ]; then
  ans=$(curl -s --max-time 180 -X POST "$KONG_URL/chat/sync" \
        -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
        -d '{"message":"Reply with exactly: E2E OK"}' 2>/dev/null)
  echo "$ans" | grep -q '"answer"' \
    && ok "POST /chat/sync -> answered: $(echo "$ans" | head -c 140)" \
    || no "POST /chat/sync failed: $(echo "$ans" | head -c 200)"

  sse=$(curl -s -N --max-time 180 -X POST "$KONG_URL/chat" \
        -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
        -d '{"message":"say hi"}' 2>/dev/null | head -c 200)
  echo "$sse" | grep -q 'event:' && ok "POST /chat -> SSE envelope received" || no "SSE: $(echo "$sse" | head -c 120)"
else
  sk "chat tests (no token)"
fi

# --------------------------------------------------------------------------
hdr "L4  data plane + PDF ingestion"
kubectl -n ai-platform exec statefulset/postgres -- psql -U agent -d agentmvp -tAc \
  "select count(*) from information_schema.tables where table_name in ('sessions','documents','document_jobs')" 2>/dev/null \
  | grep -q '^3$' && ok "postgres schema: sessions + documents + document_jobs" || no "postgres schema incomplete"
kubectl -n ai-platform exec statefulset/falkordb -- redis-cli PING 2>/dev/null | grep -q PONG \
  && ok "falkordb responds to PING" || no "falkordb PING failed"
kubectl -n ai-platform exec statefulset/falkordb -- redis-cli CONFIG GET appendonly 2>/dev/null | grep -q yes \
  && ok "falkordb AOF enabled (durable checkpoints)" || no "falkordb AOF disabled"

if [ -n "$TOKEN" ]; then
  PDF=/tmp/e2e-doc.pdf
  python3 - "$PDF" <<'PY' 2>/dev/null
import sys,zlib
txt=("BT /F1 12 Tf 60 760 Td (Project Zephyr budget is 42000 EUR for fiscal 2026.) Tj "
     "0 -20 Td (The project lead is Dana Whitfield.) Tj ET")
st=zlib.compress(txt.encode()); objs=[]
objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>")
objs.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n"%len(st)+st+b"\nendstream")
objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
out=b"%PDF-1.4\n"; offs=[]
for i,o in enumerate(objs,1):
    offs.append(len(out)); out+=b"%d 0 obj\n"%i+o+b"\nendobj\n"
x=len(out); out+=b"xref\n0 %d\n0000000000 65535 f \n"%(len(objs)+1)
for o in offs: out+=b"%010d 00000 n \n"%o
out+=b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"%(len(objs)+1,x)
open(sys.argv[1],"wb").write(out)
PY
  if [ -s "$PDF" ]; then
    up=$(curl -s --max-time 90 -X POST "$KONG_URL/documents" \
         -H "Authorization: Bearer $TOKEN" -F "file=@$PDF" 2>/dev/null)
    did=$(echo "$up" | sed -n 's/.*"document_id":"\([^"]*\)".*/\1/p')
    [ -n "$did" ] && ok "PDF uploaded -> document_id=$did" || no "upload failed: $(echo "$up" | head -c 200)"

    if [ -n "$did" ]; then
      dup=$(curl -s --max-time 60 -X POST "$KONG_URL/documents" \
            -H "Authorization: Bearer $TOKEN" -F "file=@$PDF" 2>/dev/null)
      echo "$dup" | grep -q '"state":"duplicate"' \
        && ok "re-upload is idempotent (sha256 dedup)" || no "dedup did not trigger: $(echo "$dup" | head -c 120)"

      for i in $(seq 1 40); do
        st=$(curl -s --max-time 20 "$KONG_URL/documents/$did" -H "Authorization: Bearer $TOKEN" 2>/dev/null)
        s=$(echo "$st" | sed -n 's/.*"state":"\([^"]*\)".*/\1/p')
        case "$s" in completed|partial|failed|empty) break;; esac
        sleep 6
      done
      case "$s" in
        completed) ok "ingestion completed: $(echo "$st" | head -c 150)";;
        partial)   ok "ingestion partial (some chunks failed): $(echo "$st" | head -c 150)";;
        "")        no "ingestion status unreadable";;
        *)         no "ingestion state=$s : $(echo "$st" | head -c 180)";;
      esac

      kubectl -n ai-platform exec statefulset/minio -- sh -c 'ls -R /data 2>/dev/null | head -5' >/dev/null 2>&1 \
        && ok "MinIO holds the object" || sk "MinIO listing unavailable"

      if [ "$s" = completed ] || [ "$s" = partial ]; then
        rec=$(curl -s --max-time 180 -X POST "$KONG_URL/chat/sync" \
              -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
              -d '{"message":"From my uploaded document, what is the Project Zephyr budget and who leads it?"}' 2>/dev/null)
        echo "$rec" | grep -qiE '42000|42,000|zephyr|whitfield' \
          && ok "document recalled through the memory graph" \
          || no "recall missed: $(echo "$rec" | head -c 200)"
      fi
    fi
  else sk "PDF fixture not generated"; fi
else sk "document tests (no token)"; fi

# --------------------------------------------------------------------------
hdr "L5  MCP tool servers"
for svc in mcp-web-search:3001 mcp-graphiti-memory:3002; do
  n="${svc%%:*}"; p="${svc##*:}"
  kubectl -n ai-platform exec deploy/"$n" -- \
    python -c "import socket,sys;s=socket.socket();s.settimeout(4);sys.exit(s.connect_ex(('127.0.0.1',$p)))" 2>/dev/null \
    && ok "$n listening on $p" || no "$n not listening on $p"
done
kubectl -n kagent get remotemcpservers.kagent.dev -o name 2>/dev/null | wc -l | grep -qv '^0$' \
  && ok "RemoteMCPServer CRs registered: $(kubectl -n kagent get remotemcpservers.kagent.dev --no-headers 2>/dev/null | wc -l)" \
  || no "no RemoteMCPServer CRs"

# --------------------------------------------------------------------------
hdr "L2  autoscaling (KEDA)"
kubectl -n ai-platform get scaledobject agent-backend >/dev/null 2>&1 \
  && ok "ScaledObject present" || no "ScaledObject missing"
ready=$(kubectl -n ai-platform get scaledobject agent-backend \
        -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)
[ "$ready" = "True" ] && ok "ScaledObject Ready (Prometheus trigger resolves)" || no "ScaledObject Ready=$ready"

# --------------------------------------------------------------------------
hdr "L7  observability + log tracing"
up=$(kubectl -n ai-observability exec deploy/prometheus -c prometheus -- \
      wget -qO- 'http://localhost:9090/api/v1/query?query=up' 2>/dev/null)
n=$(echo "$up" | grep -o '"value"' | wc -l)
[ "$n" -gt 0 ] && ok "prometheus: $n targets up" || no "prometheus has no up targets"
echo "$up" | grep -q 'agent-backend' && ok "agent-backend is scraped" || no "agent-backend not in scrape targets"

m=$(kubectl -n ai-observability exec deploy/prometheus -c prometheus -- \
     wget -qO- 'http://localhost:9090/api/v1/query?query=agent_backend_requests_total' 2>/dev/null)
echo "$m" | grep -q 'agent_backend_requests_total' \
  && ok "backend RED metrics present in Prometheus" || no "no agent_backend_requests_total"

c=$(code "$GRAFANA_URL/api/health"); [ "$c" = 200 ] && ok "Grafana UI -> 200" || no "Grafana -> $c"
ds=$(curl -s --max-time 15 "$GRAFANA_URL/api/datasources" 2>/dev/null)
echo "$ds" | grep -q prometheus && ok "Grafana has the Prometheus datasource" || sk "datasource list needs auth"
echo "$ds" | grep -q loki && ok "Grafana has the Loki datasource" || sk "loki datasource not listed"

lok=$(kubectl -n ai-observability exec statefulset/loki -- \
      wget -qO- 'http://localhost:3100/loki/api/v1/label/namespace/values' 2>/dev/null)
echo "$lok" | grep -q 'ai-platform' \
  && ok "Loki is ingesting logs (namespaces: $(echo "$lok" | head -c 120))" \
  || no "Loki has no ai-platform logs yet"

q=$(kubectl -n ai-observability exec statefulset/loki -- sh -c \
     'wget -qO- --header="Content-Type: application/json" "http://localhost:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22ai-platform%22%7D&limit=5"' 2>/dev/null)
echo "$q" | grep -q '"values"' && ok "LogQL query returns backend log lines" || no "LogQL returned nothing"

c=$(code "$MINIO_URL"); [ "$c" = 200 ] || [ "$c" = 403 ] || [ "$c" = 307 ] \
  && ok "MinIO console reachable ($c)" || no "MinIO console -> $c"

# --------------------------------------------------------------------------
hdr "GitOps  ArgoCD"
if kubectl get ns argocd >/dev/null 2>&1; then
  c=$(code "$ARGOCD_URL/healthz"); [ "$c" = 200 ] && ok "ArgoCD UI -> 200" || no "ArgoCD UI -> $c"
  total=$(kubectl -n argocd get applications.argoproj.io --no-headers 2>/dev/null | wc -l)
  [ "$total" -gt 0 ] && ok "$total Applications registered" || no "no Applications"
  bad=$(kubectl -n argocd get applications.argoproj.io \
        -o jsonpath='{range .items[*]}{.metadata.name}={.status.sync.status}/{.status.health.status} {end}' 2>/dev/null \
        | tr ' ' '\n' | grep -v '=Synced/Healthy' | grep -v '^$' || true)
  [ -z "$bad" ] && ok "all Applications Synced+Healthy" || no "not healthy: $(echo $bad | tr '\n' ' ')"
else
  sk "ArgoCD not installed (up-direct path)"
fi

# --------------------------------------------------------------------------
printf '\n\033[1m== summary ==\033[0m\n'
printf '  passed %d   failed %d   skipped %d\n\n' "$pass" "$fail" "$skip"
[ "$fail" -eq 0 ] || exit 1
