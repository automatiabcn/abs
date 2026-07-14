# LangFuse self-host (Helm)

```bash
# Production
helm repo add langfuse https://langfuse.github.io/langfuse-k8s
helm upgrade --install langfuse langfuse/langfuse \
  --namespace abs-observability --create-namespace \
  -f infra/helm/langfuse-values.yaml

# Local dev
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  -f infra/docker-compose.langfuse.yml \
  up -d langfuse-web langfuse-worker
# UI → http://localhost:3000
```

## Backup

`backup.schedule = "0 3 * * *"` (03:00 UTC) writes ClickHouse + Postgres snapshots
into `s3://abs-langfuse-backups/langfuse/`. Retention 30 days.

## Health checks

```bash
curl https://langfuse.abs.local/api/public/health      # 200 OK
helm status langfuse -n abs-observability
kubectl -n abs-observability get pods,pvc
```

## Troubleshooting

- **Trace ingest backpressure** → check ClickHouse memory; brief mandates ≥16Gi.
- **MinIO quota** → `kubectl exec -it minio-0 -- mc admin info local`.
- **NextAuth login loop** → `NEXTAUTH_SECRET` mismatch across replicas.
- **Bad migrations** → `helm rollback langfuse <prev-rev>`.
- **Total reset** → `helm uninstall langfuse -n abs-observability`
  (deletes PVCs only if reclaimPolicy=Delete).
