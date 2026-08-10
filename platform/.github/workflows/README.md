# .github/workflows/

GitHub Actions workflow definitions.

```mermaid
flowchart TB
    EVENT[git push / PR]
    EVENT --> CI_LINT[ci-lint.yaml<br/>ruff, mypy, helm lint, yamllint]
    EVENT --> CI_TEST[ci-test.yaml<br/>unit + integration + contract]
    EVENT --> CI_BUILD[ci-build.yaml<br/>docker build + push + cosign sign]
    EVENT --> CI_EVAL[ci-evals.yaml<br/>DeepEval + Ragas + Inspect + Promptfoo<br/>only if L3/L4/L5/L7 touched]
    EVENT --> CI_SCAN[ci-scan.yaml<br/>SBOM + trivy + grype]
    CI_BUILD -.->|"image pushed"| IU[ArgoCD Image Updater]
```

## Workflows (Stage 13 deliverable)

- `ci-lint.yaml` — Python linting, type-checking, Helm lint, YAML lint.
- `ci-test.yaml` — unit and integration tests via testcontainers; contract tests via schemathesis + AsyncAPI runner.
- `ci-build.yaml` — Docker build with BuildKit cache, push, cosign signing.
- `ci-evals.yaml` — DeepEval + Promptfoo + Ragas + Inspect AI suites; triggered only on PRs that touch `services/L3-*`, `services/L4-*`, `services/L5-*`, `services/L7-*`.
- `ci-scan.yaml` — SBOM generation, trivy vulnerability scan, grype scan.

## Gating

A PR is mergeable only when all five workflows succeed and harness thresholds (per `docs/protocols/harness-engineering.md`) are met.

## References

- Decision rationale: `docs/adr/0008-cicd-github-actions-argocd.md`.
- Stage 13 deliverables: `docs/stages/STAGE-13-cicd-gitops/README.md`.
- GitHub Actions documentation: https://docs.github.com/en/actions
- cosign: https://github.com/sigstore/cosign
- trivy: https://aquasecurity.github.io/trivy/
