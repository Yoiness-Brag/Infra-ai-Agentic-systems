# ArgoCD AppProjects

AppProject definitions. One project per platform area (cluster, data-plane, observability, gateway, orchestration, governance, agent-runtime). Each project bounds the namespaces and resource kinds its Applications may touch — defense-in-depth alongside K8s RBAC.

```mermaid
flowchart LR
    PRJ[AppProject CRD] -->|destinations| NS[Allowed namespaces]
    PRJ -->|sourceRepos| GIT[Allowed Git repos]
    PRJ -->|clusterResourceWhitelist| CLR[Allowed cluster-scoped kinds]
    PRJ -->|namespaceResourceWhitelist| NSR[Allowed namespace-scoped kinds]
    APP[Application] -->|.spec.project = name| PRJ
```

## References

- ArgoCD Projects: https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/#projects
- Decision rationale: `docs/adr/0008-cicd-github-actions-argocd.md`.
