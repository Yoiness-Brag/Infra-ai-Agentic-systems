# ArgoCD Applications

App-of-Apps children. Each YAML manifest in this folder defines one ArgoCD `Application` that targets a path under `platform/` or `services/`. ArgoCD Image Updater writes image-tag bumps here from CI per ADR-0008.

```mermaid
flowchart LR
    ROOT[platform/argocd/root.yaml<br/>App-of-Apps root] -->|references| APPS[applications/*.yaml<br/>this folder]
    APPS -->|target| K8S[Cluster resources]
    CI[GitHub Actions CI<br/>image build + push] -->|notifies| IU[ArgoCD Image Updater]
    IU -->|git commit image-tag bump| APPS
```

## References

- ArgoCD App-of-Apps pattern: https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/
- Image Updater: https://argocd-image-updater.readthedocs.io/
- Decision rationale: `docs/adr/0008-cicd-github-actions-argocd.md`.
