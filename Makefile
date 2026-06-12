SHELL := /bin/bash

CLUSTER       := infra-ai-mvp
K3D_CONFIG    := cluster/k3d/k3d-config.yaml
KONG_URL      := http://localhost:8080
JWT_ISS       := mvp-app
ARGOCD_NS     := argocd
ARGOCD_VER    := v3.4.1

IMG_BACKEND   := mvp/agent-backend:dev
IMG_WEBSEARCH := mvp/mcp-web-search:dev
IMG_MEMORY    := mvp/mcp-graphiti-memory:dev

ENV_FILE ?= $(firstword $(wildcard .env/.env.infra .env))
ifneq (,$(ENV_FILE))
include $(ENV_FILE)
export
endif

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: require-env
require-env: ## Fail-closed: ensure required .env values are set (SPEC §6)
	@test -n "$(GOOGLE_API_KEY)"    || { echo "ERROR: GOOGLE_API_KEY is empty (.env)"; exit 1; }
	@test -n "$(JWT_SECRET)"        || { echo "ERROR: JWT_SECRET is empty (.env)"; exit 1; }
	@test -n "$(POSTGRES_PASSWORD)" || { echo "ERROR: POSTGRES_PASSWORD is empty (.env)"; exit 1; }
	@echo "env OK (FALKORDB_PASSWORD is optional)" 1>&2

.PHONY: cluster
cluster: ## Create the k3d cluster (idempotent)
	@k3d cluster list $(CLUSTER) >/dev/null 2>&1 \
	  && echo "cluster $(CLUSTER) already exists" \
	  || k3d cluster create --config $(K3D_CONFIG)

.PHONY: mvp-down
mvp-down: ## Tear down: delete the k3d cluster
	k3d cluster delete $(CLUSTER)

.PHONY: build-images
build-images: ## docker build the 3 service images (SPEC §5)
	docker build -t $(IMG_BACKEND)   services/agent-backend
	docker build -t $(IMG_WEBSEARCH) services/mcp-web-search
	docker build -t $(IMG_MEMORY)    services/mcp-graphiti-memory

.PHONY: import-images
import-images: ## Import the 3 images into the k3d cluster
	k3d image import $(IMG_BACKEND) $(IMG_WEBSEARCH) $(IMG_MEMORY) -c $(CLUSTER)

.PHONY: secrets
secrets: require-env ## Create/refresh K8s Secrets from .env (idempotent)
	kubectl apply -f platform/foundation/namespaces.yaml
	kubectl create secret generic gemini-api -n kagent \
	  --from-literal=GOOGLE_API_KEY="$(GOOGLE_API_KEY)" \
	  --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic gemini-api -n ai-platform \
	  --from-literal=GOOGLE_API_KEY="$(GOOGLE_API_KEY)" \
	  --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic jwt-secret -n ai-gateway \
	  --from-literal=JWT_SECRET="$(JWT_SECRET)" --from-literal=JWT_ISS="$(JWT_ISS)" \
	  --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic jwt-secret -n ai-platform \
	  --from-literal=JWT_SECRET="$(JWT_SECRET)" --from-literal=JWT_ISS="$(JWT_ISS)" \
	  --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic postgres-creds -n ai-platform \
	  --from-literal=POSTGRES_USER="agent" \
	  --from-literal=POSTGRES_PASSWORD="$(POSTGRES_PASSWORD)" \
	  --from-literal=POSTGRES_DB="agentmvp" \
	  --dry-run=client -o yaml | kubectl apply -f -
	kubectl create secret generic falkordb-auth -n ai-platform \
	  --from-literal=FALKORDB_PASSWORD="$(FALKORDB_PASSWORD)" \
	  --dry-run=client -o yaml | kubectl apply -f -
	@echo "secrets applied"

.PHONY: install-argocd
install-argocd: ## Install ArgoCD into the cluster
	kubectl create namespace $(ARGOCD_NS) --dry-run=client -o yaml | kubectl apply -f -
	kubectl apply -n $(ARGOCD_NS) --server-side --force-conflicts \
	  -f https://raw.githubusercontent.com/argoproj/argo-cd/$(ARGOCD_VER)/manifests/install.yaml
	kubectl -n $(ARGOCD_NS) rollout status deploy/argocd-server --timeout=300s

.PHONY: mvp-up
mvp-up: cluster build-images import-images secrets install-argocd ## Full GitOps bring-up
	kubectl apply -f platform/argocd/project.yaml
	kubectl apply -f platform/argocd/root.yaml
	@echo ""
	@echo ">>> ArgoCD will now sync every layer (waves 0..4)."
	@echo ">>> NOTE: the cluster must be able to reach root.yaml's repoURL (push first)."
	@echo ">>> If you have no reachable remote, use:  make mvp-up-direct"

.PHONY: mvp-up-direct
mvp-up-direct: cluster build-images import-images secrets ## Local bring-up, kustomize/helm in wave order (no git)
	@echo "== wave 0: foundation (namespaces + default-deny netpols) =="
	kubectl apply -k platform/foundation
	@echo "== wave 1: data / kong / observability =="
	kubectl apply -k platform/data            || kubectl apply -f platform/data
	kubectl apply -k platform/kong/k8s        || kubectl apply -f platform/kong/k8s        || true
	@echo "   rendering kong-declarative configmap (jwt credential secret via envsubst; Kong env-vault cannot resolve it)"
	@command -v envsubst >/dev/null 2>&1 \
	  && { envsubst '$$JWT_SECRET' < platform/kong/kong.yaml > /tmp/kong-rendered.yaml \
	       && kubectl create configmap kong-declarative -n ai-gateway --from-file=kong.yaml=/tmp/kong-rendered.yaml --dry-run=client -o yaml | kubectl apply -f - \
	       && rm -f /tmp/kong-rendered.yaml; } \
	  || echo "   WARNING: envsubst missing (install gettext) — JWT auth will 401 until kong-declarative carries the real secret"
	kubectl apply -k platform/observability   || kubectl apply -f platform/observability   || true
	@echo "== wave 1b: kong Helm release (Gateway proxy) =="
	-helmfile -f platform/kong/helmfile.yaml apply 2>/dev/null || echo "  (helmfile/helm not present — install: helm install kong kong/kong -n ai-gateway -f platform/kong/values.yaml)"
	@echo "== wave 2: kagent control plane (helmfile + CRs) — owned by platform/kagent agent =="
	-helmfile -f platform/kagent/helmfile.yaml apply 2>/dev/null || echo "  (no kagent helmfile / helm not present)"
	kubectl apply -f platform/kagent/networkpolicy.yaml         2>/dev/null || true
	kubectl apply -f platform/kagent/model-config.yaml          2>/dev/null || true
	kubectl apply -f platform/kagent/remote-mcp-web-search.yaml 2>/dev/null || true
	kubectl apply -f platform/kagent/remote-mcp-graphiti-memory.yaml 2>/dev/null || true
	@echo "== wave 3: mcp servers =="
	kubectl apply -k services/mcp-web-search/k8s       || kubectl apply -f services/mcp-web-search/k8s       || true
	kubectl apply -k services/mcp-graphiti-memory/k8s  || kubectl apply -f services/mcp-graphiti-memory/k8s  || true
	@echo "== wave 4: agent-backend + kagent Agent CR (last — references MCP servers + ModelConfig) =="
	kubectl apply -k services/agent-backend/k8s        || kubectl apply -f services/agent-backend/k8s        || true
	kubectl apply -f platform/kagent/agent.yaml        2>/dev/null || true
	@echo ""
	@echo ">>> Direct apply done. Some layers may be owned by other agents and not yet present"
	@echo ">>> (the '|| true' guards keep this idempotent). Re-run after they land."

.PHONY: token
token: require-env ## Mint a short-lived HS256 JWT (iss=mvp-app) signed with $JWT_SECRET
	@python3 -c 'import os,sys,json,time,hmac,hashlib,base64; \
b=lambda d: base64.urlsafe_b64encode(d).rstrip(b"="); \
seg=lambda o: b(json.dumps(o,separators=(",",":")).encode()); \
h=seg({"alg":"HS256","typ":"JWT"}); \
now=int(time.time()); \
p=seg({"iss":"$(JWT_ISS)","sub":"smoke-user","iat":now,"exp":now+900}); \
msg=h+b"."+p; \
sig=b(hmac.new(os.environ["JWT_SECRET"].encode(),msg,hashlib.sha256).digest()); \
sys.stdout.write((msg+b"."+sig).decode())'

.PHONY: smoke
smoke: ## curl /chat through Kong at localhost:8080 with a fresh JWT
	@TOKEN=$$($(MAKE) -s token); \
	echo "POST $(KONG_URL)/chat (iss=$(JWT_ISS))"; \
	curl -sS -N -X POST "$(KONG_URL)/chat" \
	  -H "Authorization: Bearer $$TOKEN" \
	  -H "Content-Type: application/json" \
	  -d '{"message":"Hello from smoke test. What is 2+2?"}' \
	  || { echo "smoke FAILED (is the cluster up + Kong route /chat configured?)"; exit 1; }

.PHONY: eval
eval: require-env ## Run the Gemini LLM-as-judge eval against /chat (SPEC §13)
	@TOKEN=$$($(MAKE) -s token); \
	cd eval && JWT="$$TOKEN" GOOGLE_API_KEY="$(GOOGLE_API_KEY)" \
	  KONG_URL="$(KONG_URL)" python3 run_eval.py

.PHONY: lint
lint: ## Lint: ruff (python) + kustomize build + kubeconform/yaml (best-effort)
	-ruff check eval
	-kustomize build platform/foundation >/dev/null && echo "kustomize build platform/foundation OK"
	@command -v kubeconform >/dev/null 2>&1 \
	  && kustomize build platform/foundation | kubeconform -strict -ignore-missing-schemas -summary \
	  || echo "kubeconform not installed — skipping schema validation"
