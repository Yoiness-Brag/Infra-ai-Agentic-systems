# Secrets

Every Secret this platform needs is created imperatively by `make secrets` from `.env/.env.infra`.
Nothing in this directory is applied by kustomize or by ArgoCD — secrets are deliberately outside
GitOps reconciliation (SPEC §18). The previous `*.secret.example.yaml` files were removed because
they carried non-empty placeholder values (`REPLACE_ME_FROM_ENV`), which fail **open**: applying them
produced a Postgres that booted with a known password and a Kong that validated JWTs signed with a
committed secret. SPEC §6 requires fail-closed.

## Secrets created by `make secrets`

| Secret | Namespaces | Keys |
|---|---|---|
| `gemini-api` | `kagent`, `ai-platform`, `ai-gateway` | `GOOGLE_API_KEY` |
| `jwt-secret` | `ai-gateway`, `ai-platform` | `JWT_SECRET`, `JWT_ISS` |
| `postgres-creds` | `ai-platform` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| `falkordb-auth` | `ai-platform` | `FALKORDB_PASSWORD` (only when non-empty) |
| `minio-creds` | `ai-platform` | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` |
| `grafana-admin` | `ai-observability` | `GRAFANA_ADMIN_PASSWORD` |
| `kong-declarative` | `ai-gateway` | `kong.yml` (rendered from `platform/kong/kong.yaml` via `envsubst`) |

## Langfuse profile only (`make langfuse-up`)

| Secret | Namespace | Keys |
|---|---|---|
| `langfuse-secrets` | `ai-observability` | `SALT`, `ENCRYPTION_KEY`, `NEXTAUTH_SECRET` |
| `langfuse-postgres` | `ai-observability` | `postgres-password`, `password` |
| `langfuse-redis` | `ai-observability` | `redis-password` |
| `langfuse-clickhouse` | `ai-observability` | `password` |
| `langfuse-s3` | `ai-observability` | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` |
| `langfuse-otlp` | `ai-observability` | `LANGFUSE_OTLP_ENDPOINT`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` |

## Why `kong-declarative` is a Secret, not a ConfigMap

The Kong declarative config embeds the consumer's HS256 JWT credential. Kong's env-vault form
(`{vault://env/…}`) works only on *referenceable* schema fields; `jwt_secrets.secret` is declared
`encrypted`, **not** `referenceable`, so a vault reference is stored literally and every token 401s.
The value must therefore be materialised at deploy time. The chart's `dblessConfig.secret` accepts a
Secret with key `kong.yml`, so the credential never lands in a ConfigMap and never enters git.
