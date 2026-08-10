# platform/data — MVP data plane (`ai-platform` namespace)

Stateful backends for the kagent MVP. Conforms to `infra-code/SPEC.md` §3 (namespaces),
§4 (DNS/ports), §6 (secrets), §9 (memory & sessions).

`kustomization.yaml` bundles both for ArgoCD / `kustomize build` (sync-wave 1, SPEC §12). The
`ai-platform` namespace, its default-deny NetworkPolicy, and the `falkordb-auth` / `postgres-creds`
secrets are created at platform stand-up (wave 0) and are out of this component's scope.

## Components

| File | Resource | DNS:port | Storage | Image |
|---|---|---|---|---|
| `falkordb.yaml` | StatefulSet + headless Service + NetworkPolicy | `falkordb.ai-platform:6379` | 5Gi PVC (`/data`) | `falkordb/falkordb:v4.2.2` |
| `postgres.yaml` | StatefulSet + headless Service + init ConfigMap + NetworkPolicy | `postgres.ai-platform:5432` | 5Gi PVC | `postgres:16.4-bookworm` |

## FalkorDB (Graphiti backend)

- RESP (redis-protocol) graph store. Started via
  `redis-server --protected-mode no --dir /data --loadmodule /FalkorDB/bin/src/falkordb.so`. The
  module path is the one baked into `falkordb/falkordb:v4.2.2` (`/FalkorDB/bin/src/falkordb.so`);
  `--protected-mode no` matches the image's own `run.sh` so cross-pod RESP connections are accepted
  when no password is set. The image's native `redis` user is **uid/gid 999**, which the
  `securityContext` (`runAsUser/Group: 999`, `fsGroup: 999`) matches so the PVC at `/data` is
  writable under a read-only root filesystem.
- **Auth (optional, SPEC §6):** `FALKORDB_PASSWORD` is read from the `falkordb-auth` secret with
  `optional: true`. When present, the container starts with `--requirepass`; when absent it runs
  open (acceptable MVP shortcut on a default-deny namespace). Probes use the same password.
- **NetworkPolicy `falkordb-allow-ingress`:** ingress to 6379 allowed ONLY from pods labelled
  `app.kubernetes.io/name=agent-backend` (session-lifecycle writes) and `app=mcp-graphiti-memory`
  (the memory MCP labels its pods with the short `app` key, not `app.kubernetes.io/name`).
  Everything else is denied by the namespace default-deny.

## Postgres (session store)

- **DB/user:** `agentmvp` / `agent`, supplied via `envFrom: secretRef postgres-creds`
  (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`). **Fail-closed (SPEC §6):** no default
  password is baked in, so an empty/missing `POSTGRES_PASSWORD` makes initdb refuse to start.
- **Init ConfigMap `postgres-init`** mounts `01-sessions.sql` to `/docker-entrypoint-initdb.d/`,
  run once on first boot (empty data dir). Creates the `sessions` table per SPEC §9:

  ```sql
  CREATE TABLE IF NOT EXISTS sessions (
      session_id  uuid        PRIMARY KEY,
      app         text        NOT NULL,
      subject     text        NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now(),
      last_seen   timestamptz NOT NULL DEFAULT now(),
      meta        jsonb       NOT NULL DEFAULT '{}'::jsonb
  );
  ```
  Plus indexes on `app`, `subject`, and `last_seen`.
- `PGDATA=/var/lib/postgresql/data/pgdata` (subdir) so initdb's empty-dir check passes on the PVC.
- **NetworkPolicy `postgres-allow-ingress`:** ingress to 5432 allowed ONLY from `agent-backend`.

## Security

Both run **non-root** (`runAsNonRoot: true`, both at uid/gid 999 to match their image's native
user), drop all capabilities, no privilege escalation. FalkorDB uses a read-only root filesystem
(data on the PVC); Postgres keeps a writable rootfs for its socket/lockfiles (durable data is on the
PVC). Image tags are pinned (no `:latest`).

## Validate

```bash
kustomize build infra-code/platform/data | kubeconform -strict -summary
```
