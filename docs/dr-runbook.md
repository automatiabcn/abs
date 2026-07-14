# Disaster Recovery Runbook

> Targets: **RTO < 1 hour, RPO < 15 minutes**. Last drilled: pending the first scheduled run.

## Scope

This runbook covers full or partial loss of:

- PostgreSQL (tenant data, OAuth, audit chain).
- Qdrant (vector embeddings).
- ClickHouse (LangFuse trace store).
- NATS JetStream (event durability).
- Object storage (Cerbos audit, RAG document blobs).

It does **not** cover code-level rollbacks (use `helm rollback abs <prev-rev>`).

## Deployment modes

ABS ships in two datastore topologies. **Pick the section that matches yours.**

- **Default / zero-config (SQLite)** — `docker compose up`, no `ABS_DATABASE_URL`.
  All relational data lives in a single file, `/app/data/abs.db`. This is what
  most self-host customers run. See **SQLite default deployment** below.
- **Scaled (Postgres + Qdrant + ClickHouse + NATS)** — Helm/K8s with external
  managed datastores. See **Backup Strategy** and **Restore Procedures** below.

## SQLite default deployment

The default install keeps tenants, users, OAuth and the audit chain in
`/app/data/abs.db`, plus the age-encrypted `secrets.yaml`, on the `abs-data`
Docker volume.

> **Do not** back this up by `tar`-ing the live volume — a copy taken mid-write
> (or with an un-checkpointed WAL) can restore corrupt. Use the scripts below,
> which take a transactionally consistent online snapshot (`SQLite .backup`).

**Backup** (RPO = your cron interval; the file is small, so back up often):

```bash
# host:
docker compose exec -T backend env ABS_BACKUP_DIR=/app/data/backups \
  bash -s < scripts/dr/backup_sqlite.sh
# → /app/data/backups/abs-sqlite-<UTC>.tar.gz  (abs.db + secrets.yaml)
```

Copy the resulting bundle off-box (S3, another host) — set `ABS_DR_S3_BUCKET`
to have the script upload it for you.

**Restore** (RTO = minutes):

```bash
docker compose stop backend          # SQLite is single-writer
docker compose exec -T backend bash -s -- /app/data/backups/abs-sqlite-<UTC>.tar.gz \
  < scripts/dr/restore_sqlite.sh     # snapshots current DB to .pre-restore-* first
docker compose start backend
curl -fsS http://localhost:8000/healthz   # expect 200 {"db":"up"}
```

**Vault key (critical):** `secrets.yaml` is age-encrypted and decrypts **only**
with the vault key (`vault-key/age.key`). The backup deliberately does **not**
bundle that key — back it up **separately and securely**. Without it, a restored
`secrets.yaml` cannot be decrypted; the system falls back to plaintext `.env`.

**Drill:** `core/backend/tests/test_dr_sqlite_drill.py` round-trips a real DB
(backup → wipe → restore) and asserts the data survives with integrity intact.

## Backup Strategy

| Layer | Mechanism | Frequency | Retention | Owner |
|---|---|---|---|---|
| PostgreSQL | `pg_basebackup` + WAL streaming to S3 | continuous | 30 days | DB on-call |
| Qdrant | snapshot via `/collections/<name>/snapshots` | hourly | 7 days | RAG on-call |
| ClickHouse | `BACKUP DATABASE … TO Disk('s3', …)` | hourly | 14 days | Observability |
| NATS JetStream | replicated stream (R=3) + S3 jetstream object store | continuous | 7 days | Platform |
| Object storage | versioned bucket + cross-region replication | continuous | 90 days | Platform |
| Cerbos audit log | append-only S3 + HMAC chain | continuous | 7 years (SOC2) | Security |

## Restore Procedures

### Postgres point-in-time

```bash
# Identify last good base backup.
aws s3 ls s3://abs-pg-backups/base/ | tail -5

# Stop backend pods to avoid writes during restore.
kubectl -n abs-prod scale deploy/abs-abs-backend --replicas=0

# Restore base + replay WAL up to incident timestamp.
pg_basebackup -D /var/lib/postgresql/restore -F t -X stream -P
recovery_target_time = '2026-04-28 10:30:00 UTC'

# Promote, point ABS at the restored cluster (helm value), scale back up.
helm upgrade abs ./infra/helm/abs --reuse-values \
  --set state.postgresUrl="postgres://…/restored"
kubectl -n abs-prod scale deploy/abs-abs-backend --replicas=3
```

### Qdrant collection

```bash
# From the most recent hourly snapshot.
curl -fsS -X PUT "http://qdrant:6333/collections/abs_documents/snapshots/upload?priority=replica" \
  -H 'api-key: $QDRANT_KEY' \
  -F snapshot=@./abs_documents_2026-04-28T10:00:00.snapshot
```

### NATS JetStream

NATS R=3 should self-heal. If the entire cluster is lost, recover from the S3 object store:

```bash
nats stream restore ABS-EVENTS s3://abs-nats-backups/abs-events/latest.tar.zst
```

## Drill Procedure (Monthly)

The drill is automated by a CronJob (`infra/helm/abs/templates/cron-dr-drill.yaml`)
running on the 1st of every month at 03:00 UTC, but humans must observe and
sign off:

1. Snapshot all 5 layers in **staging**.
2. Drop the staging Postgres + Qdrant data.
3. Restore from latest snapshots.
4. Run the smoke suite (`pytest tests/smoke -k dr_drill`).
5. Record durations in `benchmarks/results/dr-YYYY-MM.json`.
6. Update this runbook if any step diverged.

## RTO / RPO Validation

| Layer | RTO target | RPO target | Last measured |
|---|---|---|---|
| Postgres | 30 min | 5 min | TBD |
| Qdrant | 20 min | 1 hour | TBD |
| ClickHouse | 30 min | 1 hour | TBD |
| NATS | 5 min | 0 (replicated) | TBD |
| Cerbos audit | 60 min | 15 min | TBD |

Filing the first measured numbers and any breach analysis is the close-out
artifact for the drill.

## Contacts

- DB on-call: PagerDuty `abs-db`
- RAG on-call: PagerDuty `abs-rag`
- Platform on-call: PagerDuty `abs-platform`
- Security: `security@abs-server.example.com` (PGP key on the public security page)
