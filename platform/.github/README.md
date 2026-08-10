# .github/

CI configuration and GitHub-specific automation. ArgoCD is the *deployment* mechanism (ADR-0008); GitHub Actions is the *CI* mechanism that produces images, runs tests, runs the harness, and notifies ArgoCD Image Updater of new images.

```mermaid
flowchart LR
    DEV[Developer push] --> GHA[GitHub Actions<br/>workflows/]
    GHA -->|build| IMG[Container image]
    GHA -->|push| REG[Container registry]
    GHA -->|"test pyramid<br/>unit→integration→contract<br/>→load→DeepEval+Ragas+Inspect+Promptfoo"| GATES[CI gates]
    GATES -->|"all pass"| OK[PR mergeable]
    REG -.->|new image tag| IU[ArgoCD Image Updater]
    IU -->|git commit tag bump| GIT[Git]
    GIT -->|sync| ARGOCD[ArgoCD]
    ARGOCD -->|reconcile| CLUSTER[K3s cluster]
```

## Contents

- `workflows/` — GitHub Actions workflow definitions for CI.

## References

- Decision rationale: `docs/adr/0008-cicd-github-actions-argocd.md`.
- Testing strategy: `docs/protocols/testing-strategy.md`.
- Harness engineering: `docs/protocols/harness-engineering.md`.
