# Polish Round — R9 — Test data reset (manual gate)

**Status:** scaffolded; awaits founder approval to execute the destructive
`--confirm` step. Brief 4 R7 (TEST_DATA_CLEANUP, commit `70c1518`) shipped
the script; the polish round only verifies the dry-run command and asks
for explicit operator sign-off before purging real DB rows.

## Why we did not auto-run

`scripts/reset_test_data.py --confirm` deletes:

* All test admin users matching the `*-scan@test.local`, `final-1778…`,
  and friends regex.
* RAG documents `guvenlik_politikasi.md`, `satis_q2_raporu.pdf`,
  `musteri_destek_sss.txt` (with `--purge-rag`).
* `marketplace.install` audit events tied to test plugins (subject to
  audit-chain integrity guard inside the script).

Auto mode rule (CLAUDE.md §"Executing actions with care"): destructive
operations require explicit user confirmation even when --confirm is
available. Worker stops at dry-run.

## Reproduction

The script needs the production SQLite path and a writable `/app/data`
mount, so it must run inside the backend container — not on the host.

```bash
docker compose -f infra/docker-compose.yml exec backend \
  python /app/scripts/reset_test_data.py --dry-run

docker compose -f infra/docker-compose.yml exec backend \
  python /app/scripts/reset_test_data.py --dry-run --purge-rag
```

If the dry-run report looks correct (only test fixtures listed, no real
beta tenant rows), promote to `--confirm`:

```bash
docker compose -f infra/docker-compose.yml exec backend \
  python /app/scripts/reset_test_data.py --confirm --purge-rag
```

## What to verify after promotion

1. `/admin/users` no longer lists `*-scan@test.local`, `final-1778…` etc.
2. `/admin/rag` no longer lists `guvenlik_politikasi.md`,
   `satis_q2_raporu.pdf`, `musteri_destek_sss.txt`.
3. `/v1/admin/audit/recent` still validates (audit chain hash unbroken).
4. pytest 1845 → ≥1850 still green (no test depends on test fixtures
   being present in prod DB).

## Why no automated test

The brief explicitly couples this gate to a founder decision; baking it
into CI would defeat the safety check. The polish round logs this file
as the audit trail.
