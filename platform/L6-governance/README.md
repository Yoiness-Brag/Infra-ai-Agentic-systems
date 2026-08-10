# L6 — Safety, Policy and Governance

Cross-cutting enforcement: admission validation, certificate issuance, namespace defaults.

```mermaid
flowchart LR
    APPLY[kubectl/ArgoCD apply] -->|K8s API| ADM[Admission webhook]
    ADM --> OPA[OPA Gatekeeper<br/>constraint catalog]
    OPA -->|allow| ETCD[(etcd)]
    OPA -->|deny + audit event| NATS[NATS audit.*]
    KONG[Kong Ingress] -->|cert request| CM[cert-manager]
    CM -->|ACME| LE[Let's Encrypt]
    LE -->|TLS Secret| KONG
```

## Contents

- `opa-gatekeeper/` — ConstraintTemplates and Constraints.
- `cert-manager/` — ClusterIssuers and per-workload Issuers.

## References

- Layer specification: `docs/layers/L6-safety-policy-governance/README.md`.
- OPA Gatekeeper docs: https://open-policy-agent.github.io/gatekeeper/website/docs/
- cert-manager docs: https://cert-manager.io/docs/
