SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

CLUSTER       ?= infra-ai-mvp
K3D_CONFIG    := cluster/k3d/k3d-config.yaml
K3D_MEMORY    ?= 8g
DATA_DIR      ?= $(HOME)/.k3d-$(CLUSTER)/storage

KONG_URL      ?= http://localhost:8080
ARGOCD_URL    ?= http://localhost:8081
GRAFANA_URL   ?= http://localhost:3000
LANGFUSE_URL  ?= http://localhost:3001
MINIO_URL     ?= http://localhost:9001
FALKOR_UI_URL ?= http://localhost:3002
PGADMIN_URL   ?= http://localhost:5050

JWT_ISS       ?= mvp-app
ARGOCD_NS     := argocd

KAGENT_CHART_VERSION ?= 0.9.12
KONG_CHART_VERSION   ?= 3.4.1
KEDA_CHART_VERSION   ?= 2.20.2
LANGFUSE_CHART_VERSION ?= 1.5.41

IMG_BACKEND   := mvp/agent-backend:dev
IMG_WEBSEARCH := mvp/mcp-web-search:dev
IMG_MEMORY    := mvp/mcp-graphiti-memory:dev

ENV_FILE ?= $(firstword $(wildcard .env/.env.dev .env/.env.infra .env))
LOADENV  := set -a; . $(CURDIR)/$(ENV_FILE); set +a

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | sort | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: require-tools
require-tools: ## Fail unless every required CLI is on PATH
	@missing=0; for t in docker k3d kubectl helm kustomize argocd yq envsubst openssl python3; do \
	  command -v $$t >/dev/null 2>&1 || { echo "MISSING TOOL: $$t"; missing=1; }; \
	done; \
	[ $$missing -eq 0 ] || { echo "install the tools above, then re-run"; exit 1; }; \
	echo "tools OK"

.PHONY: require-env
require-env: ## Fail-closed: every required secret must be non-empty
	@test -n "$(ENV_FILE)" || { echo "ERROR: no .env/.env.infra or .env found"; exit 1; }
	@$(LOADENV); missing=0; \
	for v in GOOGLE_API_KEY JWT_SECRET POSTGRES_PASSWORD MINIO_ROOT_USER MINIO_ROOT_PASSWORD GRAFANA_ADMIN_PASSWORD PGADMIN_DEFAULT_PASSWORD; do \
	  [ -n "$${!v:-}" ] || { echo "ERROR: $$v is empty in $(ENV_FILE)"; missing=1; }; \
	done; \
	[ $$missing -eq 0 ] || exit 1; \
	echo "env OK (FALKORDB_PASSWORD optional)" 1>&2

.PHONY: preflight
preflight: require-tools require-env ## Tools + env + host RAM check
	@free -m | awk '/^Mem:/ {avail=$$7; want=6144; \
	  printf "host RAM available: %d MiB (core profile needs ~%d MiB)\n", avail, want; \
	  if (avail < want) printf "  WARNING: below the core-profile budget; expect evictions\n"}'

.PHONY: cluster
cluster: ## Create the k3d cluster (idempotent), with a host-backed PVC dir
	@mkdir -p "$(DATA_DIR)"
	@if k3d cluster list $(CLUSTER) >/dev/null 2>&1; then \
	  echo "cluster $(CLUSTER) already exists"; \
	else \
	  k3d cluster create --config $(K3D_CONFIG) \
	    --servers-memory $(K3D_MEMORY) \
	    --volume "$(DATA_DIR):/var/lib/rancher/k3s/storage@server:0"; \
	fi
	@kubectl cluster-info >/dev/null

.PHONY: down
down: ## Delete the k3d cluster (PVC data under $(DATA_DIR) survives)
	k3d cluster delete $(CLUSTER)

.PHONY: nuke
nuke: down ## Delete the cluster AND its persisted volumes
	rm -rf "$(DATA_DIR)"

.PHONY: build-images
build-images: ## Build the three service images
	docker build -t $(IMG_BACKEND)   services/agent-backend
	docker build -t $(IMG_WEBSEARCH) services/mcp-web-search
	docker build -t $(IMG_MEMORY)    services/mcp-graphiti-memory

.PHONY: import-images
import-images: ## Import the three images into k3d
	k3d image import $(IMG_BACKEND) $(IMG_WEBSEARCH) $(IMG_MEMORY) -c $(CLUSTER)

.PHONY: namespaces
namespaces: ## Apply namespaces + quotas + priority classes + default-deny (wave 0)
	kubectl apply -k platform/foundation

.PHONY: secrets
secrets: require-env namespaces ## Create every Secret from $(ENV_FILE) (idempotent, never committed)
	@$(LOADENV); \
	mk() { kubectl create secret generic "$$1" -n "$$2" "$${@:3}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null; echo "  secret/$$1 -n $$2"; }; \
	for ns in kagent ai-platform ai-gateway; do \
	  mk gemini-api $$ns --from-literal=GOOGLE_API_KEY="$$GOOGLE_API_KEY"; \
	done; \
	for ns in ai-gateway ai-platform; do \
	  mk jwt-secret $$ns --from-literal=JWT_SECRET="$$JWT_SECRET" --from-literal=JWT_ISS="$(JWT_ISS)"; \
	done; \
	mk postgres-creds ai-platform \
	  --from-literal=POSTGRES_USER="$${POSTGRES_USER:-agent}" \
	  --from-literal=POSTGRES_PASSWORD="$$POSTGRES_PASSWORD" \
	  --from-literal=POSTGRES_DB="$${POSTGRES_DB:-agentmvp}"; \
	mk minio-creds ai-platform \
	  --from-literal=MINIO_ROOT_USER="$$MINIO_ROOT_USER" \
	  --from-literal=MINIO_ROOT_PASSWORD="$$MINIO_ROOT_PASSWORD"; \
	mk grafana-admin ai-observability --from-literal=GRAFANA_ADMIN_PASSWORD="$$GRAFANA_ADMIN_PASSWORD"; \
	mk pgadmin-creds ai-platform \
	  --from-literal=PGADMIN_DEFAULT_EMAIL="$${PGADMIN_DEFAULT_EMAIL:-admin@infra-ai.local}" \
	  --from-literal=PGADMIN_DEFAULT_PASSWORD="$$PGADMIN_DEFAULT_PASSWORD"; \
	if [ -n "$${FALKORDB_PASSWORD:-}" ]; then \
	  mk falkordb-auth ai-platform --from-literal=FALKORDB_PASSWORD="$$FALKORDB_PASSWORD"; \
	else \
	  echo "  (FALKORDB_PASSWORD empty — skipping falkordb-auth so optional:true works)"; \
	fi
	@$(MAKE) --no-print-directory kong-config

.PHONY: kong-config
kong-config: ## Render the Kong declarative config into a Secret (holds the JWT HMAC key)
	@$(LOADENV); \
	umask 077; TMP="$$(mktemp)"; trap 'rm -f "$$TMP"' EXIT; \
	envsubst '$$JWT_SECRET' < platform/kong/kong.yaml > "$$TMP"; \
	grep -q '$${JWT_SECRET}' "$$TMP" && { echo "ERROR: envsubst did not substitute JWT_SECRET"; exit 1; } || true; \
	kubectl create secret generic kong-declarative -n ai-gateway \
	  --from-file=kong.yml="$$TMP" --dry-run=client -o yaml | kubectl apply -f - >/dev/null; \
	echo "  secret/kong-declarative -n ai-gateway (key kong.yml)"
	@kubectl -n ai-gateway rollout restart deploy/kong-kong 2>/dev/null || true

.PHONY: install-argocd
install-argocd: ## Install ArgoCD (trimmed) and expose it on $(ARGOCD_URL)
	kubectl create namespace $(ARGOCD_NS) --dry-run=client -o yaml | kubectl apply -f -
	kustomize build platform/argocd/install | kubectl apply -n $(ARGOCD_NS) --server-side --force-conflicts -f -
	kubectl -n $(ARGOCD_NS) rollout status deploy/argocd-server --timeout=600s
	kubectl -n $(ARGOCD_NS) rollout status deploy/argocd-repo-server --timeout=600s

.PHONY: install-keda
install-keda: ## Install KEDA (pinned resources)
	helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
	helm repo update kedacore >/dev/null
	helm upgrade --install keda kedacore/keda -n keda --create-namespace \
	  --version $(KEDA_CHART_VERSION) -f platform/keda/values.yaml --wait --timeout 10m

.PHONY: install-kong
install-kong: ## Install the Kong AI Gateway Helm release
	helm repo add kong https://charts.konghq.com >/dev/null 2>&1 || true
	helm repo update kong >/dev/null
	helm upgrade --install kong kong/kong -n ai-gateway \
	  --version $(KONG_CHART_VERSION) -f platform/kong/values.yaml --wait --timeout 10m

.PHONY: install-kagent
install-kagent: ## Install the kagent CRDs + controller
	helm upgrade --install kagent-crds oci://ghcr.io/kagent-dev/kagent/helm/kagent-crds \
	  -n kagent --create-namespace --version $(KAGENT_CHART_VERSION) --wait --timeout 10m
	helm upgrade --install kagent oci://ghcr.io/kagent-dev/kagent/helm/kagent \
	  -n kagent --version $(KAGENT_CHART_VERSION) -f platform/kagent/values.yaml --wait --timeout 15m

.PHONY: up
up: preflight cluster build-images import-images secrets install-argocd ## Full local bring-up via ArgoCD (GitOps)
	kubectl apply -f platform/argocd/project.yaml
	kubectl apply -f platform/argocd/root.yaml
	@echo ""
	@echo ">>> ArgoCD is syncing waves 0..5. Watch with:  make argocd-status"
	@echo ">>> UI: $(ARGOCD_URL)   password: make argocd-password"

.PHONY: up-direct
up-direct: preflight cluster build-images import-images secrets ## Local bring-up without ArgoCD (helm + kustomize, wave order)
	@echo "== wave 0: foundation =="
	kubectl apply -k platform/foundation
	@echo "== wave 1: data plane =="
	kubectl apply -k platform/data
	@echo "== wave 1: keda =="
	$(MAKE) --no-print-directory install-keda
	@echo "== wave 1: kong =="
	$(MAKE) --no-print-directory install-kong
	$(MAKE) --no-print-directory kong-config
	kubectl apply -k platform/kong/k8s
	@echo "== wave 1: observability =="
	kubectl apply -k platform/observability
	@echo "== wave 2: kagent control plane =="
	$(MAKE) --no-print-directory install-kagent
	kubectl apply -f platform/kagent/networkpolicy.yaml
	kubectl apply -f platform/kagent/model-config.yaml
	@echo "== wave 3: mcp servers =="
	kubectl apply -k services/mcp-web-search/k8s
	kubectl apply -k services/mcp-graphiti-memory/k8s
	kubectl apply -f platform/kagent/remote-mcp-web-search.yaml
	kubectl apply -f platform/kagent/remote-mcp-graphiti-memory.yaml
	@echo "== wave 4: agent-backend + Agent CR =="
	kubectl apply -k services/agent-backend/k8s
	kubectl apply -f platform/kagent/agent.yaml
	@echo ""
	@$(MAKE) --no-print-directory verify

.PHONY: langfuse-up
langfuse-up: require-env ## Install self-hosted Langfuse (needs K3D_MEMORY>=11g and ~11 GiB free host RAM)
	@$(LOADENV); \
	mk() { kubectl create secret generic "$$1" -n ai-observability "$${@:2}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null; echo "  secret/$$1"; }; \
	mk langfuse-secrets --from-literal=SALT="$$LANGFUSE_SALT" \
	  --from-literal=ENCRYPTION_KEY="$$LANGFUSE_ENCRYPTION_KEY" \
	  --from-literal=NEXTAUTH_SECRET="$$LANGFUSE_NEXTAUTH_SECRET"; \
	mk langfuse-postgres --from-literal=postgres-password="$$LANGFUSE_POSTGRES_PASSWORD" \
	  --from-literal=password="$$LANGFUSE_POSTGRES_PASSWORD"; \
	mk langfuse-redis --from-literal=redis-password="$$LANGFUSE_REDIS_PASSWORD"; \
	mk langfuse-clickhouse --from-literal=password="$$LANGFUSE_CLICKHOUSE_PASSWORD"; \
	mk langfuse-s3 --from-literal=MINIO_ROOT_USER="$$MINIO_ROOT_USER" \
	  --from-literal=MINIO_ROOT_PASSWORD="$$MINIO_ROOT_PASSWORD"
	helm repo add langfuse https://langfuse.github.io/langfuse-k8s >/dev/null 2>&1 || true
	helm repo update langfuse >/dev/null
	helm upgrade --install langfuse langfuse/langfuse -n ai-observability \
	  --version $(LANGFUSE_CHART_VERSION) -f platform/langfuse/values.yaml --wait --timeout 20m
	kubectl apply -f platform/langfuse/networkpolicy.yaml
	@echo ">>> Langfuse UI: $(LANGFUSE_URL)"

.PHONY: langfuse-down
langfuse-down: ## Remove the Langfuse profile
	-helm uninstall langfuse -n ai-observability
	-kubectl delete -f platform/langfuse/networkpolicy.yaml --ignore-not-found

.PHONY: verify
verify: ## Health-check every layer and fail on the first broken one
	@bash scripts/verify.sh

.PHONY: argocd-password
argocd-password: ## Print the ArgoCD admin password
	@kubectl -n $(ARGOCD_NS) get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo

.PHONY: argocd-login
argocd-login: ## Log the argocd CLI in against $(ARGOCD_URL)
	@argocd login localhost:8081 --username admin \
	  --password "$$($(MAKE) -s argocd-password)" --insecure --plaintext
	@argocd app list

.PHONY: argocd-status
argocd-status: ## Show sync/health of every Application
	@kubectl -n $(ARGOCD_NS) get applications.argoproj.io \
	  -o custom-columns=NAME:.metadata.name,WAVE:'.metadata.annotations.argocd\.argoproj\.io/sync-wave',SYNC:.status.sync.status,HEALTH:.status.health.status

.PHONY: urls
urls: ## Print every UI/endpoint
	@echo "Kong gateway   $(KONG_URL)      (POST /chat, /documents, GET /docs)"
	@echo "Swagger UI     $(KONG_URL)/docs"
	@echo "ArgoCD         $(ARGOCD_URL)    (admin / make argocd-password)"
	@echo "Grafana        $(GRAFANA_URL)   (admin / GRAFANA_ADMIN_PASSWORD in $(ENV_FILE))"
	@echo "MinIO console  $(MINIO_URL)     (MINIO_ROOT_USER / MINIO_ROOT_PASSWORD)"
	@echo "FalkorDB UI    $(FALKOR_UI_URL)      (graph memory browser; connect host=localhost port=6379)"
	@echo "pgAdmin        $(PGADMIN_URL)      (PGADMIN_DEFAULT_EMAIL / PGADMIN_DEFAULT_PASSWORD in $(ENV_FILE))"
	@echo "Langfuse       $(LANGFUSE_URL)  (only after: make langfuse-up)"

.PHONY: token
token: require-env ## Mint a short-lived HS256 JWT for testing
	@$(LOADENV); JWT_ISS="$(JWT_ISS)" python3 scripts/mint_token.py

.PHONY: smoke
smoke: ## End-to-end smoke test through Kong
	@bash scripts/smoke.sh

.PHONY: eval
eval: require-env ## Run the Gemini LLM-as-judge eval against /chat
	@$(LOADENV); TOKEN="$$($(MAKE) -s token)"; \
	cd eval && JWT="$$TOKEN" GOOGLE_API_KEY="$$GOOGLE_API_KEY" KONG_URL="$(KONG_URL)" python3 run_eval.py

.PHONY: lint
lint: ## Validate every manifest tree
	@bash scripts/lint.sh

.PHONY: e2e
e2e: ## Full end-to-end acceptance sweep (curl + kubectl + argocd, every layer)
	@bash scripts/e2e.sh

.PHONY: ui-up
ui-up: ## Force the on-demand UIs (pgAdmin, FalkorDB browser) up now, outside their cron window
	kubectl -n ai-platform scale deploy/pgadmin deploy/falkordb-browser --replicas=1
	kubectl -n ai-platform rollout status deploy/pgadmin --timeout=300s
	kubectl -n ai-platform rollout status deploy/falkordb-browser --timeout=300s
	@echo "FalkorDB browser: kubectl -n ai-platform port-forward svc/falkordb-browser 3002:3000"
	@echo "pgAdmin        : kubectl -n ai-platform port-forward svc/pgadmin 5050:80"

.PHONY: ui-down
ui-down: ## Scale the on-demand UIs back to zero and reclaim ~320 MiB
	kubectl -n ai-platform scale deploy/pgadmin deploy/falkordb-browser --replicas=0
