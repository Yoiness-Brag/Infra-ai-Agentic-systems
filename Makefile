SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

INFRA := infra-code

K3D_MEMORY   ?= 8g
KONG_URL     ?= http://localhost:8080
ARGOCD_URL   ?= http://localhost:8081
GRAFANA_URL  ?= http://localhost:3000
LANGFUSE_URL ?= http://localhost:3001
MINIO_URL    ?= http://localhost:9001

REMOTE_NAME ?= origin
BRANCH      ?= main

define delegate
@$(MAKE) --no-print-directory -C $(INFRA) $(1) K3D_MEMORY=$(K3D_MEMORY)
endef

.PHONY: help
help: ## List available targets
	@awk 'BEGIN{FS=":.*##"; printf "\nInfra-ai-Agentic-systems\n\nTargets:\n"} \
	  /^[a-zA-Z_.-]+:.*##/{printf "  \033[36m%-22s\033[0m %s\n",$$1,$$2} \
	  /^# ==/{printf "\n"}' $(MAKEFILE_LIST)
	@echo ""

# == Platform lifecycle =======================================================

.PHONY: preflight
preflight: ## Check tools, credentials and host RAM before anything else
	$(call delegate,preflight)

.PHONY: local-up
local-up: ## Provision k3d + ArgoCD and sync the whole platform via GitOps
	$(call delegate,up)

.PHONY: local-up-direct
local-up-direct: ## Provision k3d and apply every layer directly (no git remote needed)
	$(call delegate,up-direct)

.PHONY: local-down
local-down: ## Delete the local cluster (PVC data survives)
	$(call delegate,down)

.PHONY: nuke
nuke: ## Delete the cluster AND its persisted volumes
	$(call delegate,nuke)

.PHONY: verify
verify: ## Health-check every layer L1..L7 and fail on the first break
	$(call delegate,verify)

.PHONY: urls
urls: ## Print every UI endpoint
	$(call delegate,urls)

# == Images and secrets =======================================================

.PHONY: build-images
build-images: ## Build the three service images
	$(call delegate,build-images)

.PHONY: import-images
import-images: ## Import the three images into k3d
	$(call delegate,import-images)

.PHONY: secrets
secrets: ## Create every K8s Secret from .env/.env.dev (never committed)
	$(call delegate,secrets)

# == ArgoCD ===================================================================

.PHONY: argocd-install
argocd-install: ## Install ArgoCD (trimmed, NodePort 30081)
	$(call delegate,install-argocd)

.PHONY: argocd-apps
argocd-apps: ## Apply the AppProject and the App-of-Apps root
	kubectl apply -f $(INFRA)/platform/argocd/project.yaml
	kubectl apply -f $(INFRA)/platform/argocd/root.yaml

.PHONY: argocd-password
argocd-password: ## Print the ArgoCD admin password
	$(call delegate,argocd-password)

.PHONY: argocd-login
argocd-login: ## Log the argocd CLI in against $(ARGOCD_URL)
	$(call delegate,argocd-login)

.PHONY: argocd-status
argocd-status: ## Sync + health of every Application, by wave
	$(call delegate,argocd-status)

.PHONY: argocd-sync
argocd-sync: ## Force-sync every Application and wait for Healthy
	argocd app sync -l argocd.argoproj.io/instance --prune --timeout 900 || true
	argocd app wait -l argocd.argoproj.io/instance --health --timeout 900

.PHONY: argocd-ui
argocd-ui: ## Open the ArgoCD UI (prints URL + credentials)
	@echo "ArgoCD UI : $(ARGOCD_URL)"
	@echo "user      : admin"
	@printf 'password  : '; $(MAKE) --no-print-directory -C $(INFRA) argocd-password

# == Agent =====================================================================

.PHONY: token
token: ## Mint a short-lived HS256 JWT for testing
	$(call delegate,token)

.PHONY: smoke
smoke: ## POST /chat and /chat/sync through Kong with a fresh JWT
	$(call delegate,smoke)

.PHONY: eval
eval: ## Run the Gemini LLM-as-judge evaluation against /chat
	$(call delegate,eval)

# == Observability ============================================================

.PHONY: langfuse-up
langfuse-up: ## Install self-hosted Langfuse (needs K3D_MEMORY>=11g)
	$(call delegate,langfuse-up)

.PHONY: langfuse-down
langfuse-down: ## Remove the Langfuse profile
	$(call delegate,langfuse-down)

# == Quality ==================================================================

.PHONY: lint
lint: ## Validate every manifest tree, chart and Python package
	$(call delegate,lint)

.PHONY: test
test: ## Run the backend regression suite
	@cd $(INFRA)/services/agent-backend && uv run pytest -q

.PHONY: docs-check
docs-check: ## Validate that every layer and stage folder has its required documents
	@bash scripts/docs-check.sh

.PHONY: lint-docs
lint-docs: ## Lint Markdown files
	@command -v markdownlint >/dev/null 2>&1 || { echo "markdownlint not installed; skipping"; exit 0; }
	@markdownlint 'docs/**/*.md' 'README.md' 'ARCHITECTURE.md'

.PHONY: mmd-render
mmd-render: ## Render all Mermaid diagrams to PNG (requires mermaid-cli)
	@command -v mmdc >/dev/null 2>&1 || { echo "mermaid-cli not installed; skipping"; exit 0; }
	@find docs platform -name '*.mmd' -print0 | xargs -0 -I{} mmdc -i {} -o {}.png

# == GitOps remote ============================================================

.PHONY: remote-check
remote-check: ## Verify the ArgoCD repoURL is reachable (GitOps precondition)
	@url="$$(yq -r '.spec.source.repoURL' $(INFRA)/platform/argocd/root.yaml)"; \
	echo "repoURL: $$url"; \
	git ls-remote "$$url" >/dev/null 2>&1 \
	  && echo "reachable — 'make local-up' can sync" \
	  || { echo "NOT reachable. ArgoCD clones over the network, so GitOps cannot work."; \
	       echo "Either push this repo to that URL, or use 'make local-up-direct'."; exit 1; }

.PHONY: push
push: ## Commit and push to $(REMOTE_NAME)/$(BRANCH) (authenticate first)
	@git remote get-url $(REMOTE_NAME) >/dev/null 2>&1 \
	  || { echo "no '$(REMOTE_NAME)' remote. Add one:"; \
	       echo "  git remote add $(REMOTE_NAME) https://github.com/<owner>/<repo>.git"; exit 1; }
	git add -A
	@git diff --cached --quiet && echo "nothing to commit" || git commit -m "$(or $(MSG),chore: sync infra-code)"
	git push -u $(REMOTE_NAME) $(BRANCH)
	@$(MAKE) --no-print-directory remote-check
