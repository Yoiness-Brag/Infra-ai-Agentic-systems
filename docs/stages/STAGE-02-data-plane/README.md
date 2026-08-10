# Stage 02 — Data Plane (L4 stores)

## Goal

Install the four data stores that L4 memory-svc will sit on top of: Postgres, Qdrant, FalkorDB, Redis. Plus the Langfuse-side stores (ClickHouse, MinIO) and the Postgres + Redis instances Langfuse v3 needs.

## Depends on

Stage 01.

## Deliverables

- Helm-deployed Postgres (CloudNativePG operator preferred), Qdrant, FalkorDB, Redis under `platform/L4-data-plane/`.
- ClickHouse and MinIO under `platform/L7-observability/` (consumed by Langfuse in Stage 03).
- ArgoCD Applications wiring each chart to the cluster.
- Backup policy (Postgres WAL archiving, FalkorDB RDB, Redis AOF).

## Non-goals

- No application logic deployed yet. The stores stand alone; memory-svc is Stage 08.

## Acceptance criteria

1. All seven stores Ready in their namespaces.
2. Each store passes a smoke test (write a key, read it back).
3. Backups configured and a restore drill scripted under `platform/L4-data-plane/*/restore.sh`.

## Next stage

Stage 03 (Observability) and Stage 08 (Memory).
