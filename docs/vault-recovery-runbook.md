# Vault Recovery Runbook

This document covers four disaster scenarios for the ABS sops + age vault. Run
the prechecks first; do not skip the verification step at the end.

> **Audience:** ABS solo operator (you). All commands assume `cd /opt/abs` on
> the production host and that the Docker compose stack is up.
>
> **Time budget:** scenario 1–2 should complete in under 15 minutes. Scenario
> 3 (vault corruption) depends on backup retrieval time.

---

## Quick reference

| Scenario | Trigger | Recovery time | Data loss risk |
|---|---|:-:|:-:|
| 1. Master key file deleted | `ls vault-key/age.txt` → no such file | 5 min | None (escrow restore) |
| 2. Master key compromised | Suspect leak (Slack paste, wrong commit) | 10 min | None (rotation) |
| 3. Vault file corrupted | `sops -d secrets.yaml` fails parsing | 15-60 min | Depends on backup recency |
| 4. Partial secret corruption | One key returns garbage, others OK | 10 min | One secret only |

---

## Scenario 1 — Master key file deleted

**Symptom**

```bash
docker compose exec backend sops -d /app/data/secrets.yaml
# Failed to get the data key from any of the keys
```

**Precheck**

```bash
ls -la /opt/abs/infra/vault-key/        # age.txt missing
docker compose logs backend | grep -i vault | tail -20
```

**Recovery**

```bash
# 1. Stop backend so it stops trying to decrypt with no key
docker compose stop backend

# 2. Restore master key from your escrow store. Pick ONE:

# (a) 1Password CLI
op document get "ABS Production Vault Master Key" \
    --vault "ABS Production" \
    --output /opt/abs/infra/vault-key/age.txt

# (b) S3 with KMS
aws s3 cp s3://abs-vault-escrow/age.txt \
    /opt/abs/infra/vault-key/age.txt --sse aws:kms

# (c) Encrypted ZIP
7z x -p"$(security find-generic-password -w -s 'abs-vault-escrow')" \
    escrow-2026-04-27.7z -o/opt/abs/infra/vault-key/

# 3. Lock down permissions
chmod 600 /opt/abs/infra/vault-key/age.txt
chown root:root /opt/abs/infra/vault-key/age.txt

# 4. Restart backend
docker compose start backend
docker compose logs -f backend | grep -i vault
```

**Verification**

```bash
docker compose exec backend python -c "
from app.vault.runner import decrypt_all
print(list(decrypt_all().keys()))
"
# Expect a non-empty list of secret keys.

curl -fsS https://abs.your-domain.com/v1/health/full | jq '.checks[] | select(.name=="vault")'
# Expect ok=true
```

**Post-mortem checklist**

- Why did the key file disappear? (volume unmount, accidental rm, container rebuild?)
- Are escrow snapshots up to date? Last backup timestamp?
- Has every laptop/server with a key copy been audited?

---

## Scenario 2 — Master key compromised

**Symptom**

You discover the key file was committed to a public git repository, pasted into
Slack, or otherwise leaked. **Treat as a P0 incident.**

**Precheck**

```bash
# Snapshot the current vault before doing anything
cp /opt/abs/data/secrets.yaml /opt/abs/data/secrets.yaml.preincident
cp /opt/abs/infra/vault-key/age.txt /opt/abs/infra/vault-key/age.txt.preincident
```

**Recovery**

```bash
# 1. Rotate via admin API (preferred — atomic + audit logged)
curl -X POST https://abs.your-domain.com/v1/admin/vault/rotate-key \
  -H "Authorization: Bearer $ABS_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"compromise"}'

# Expected response:
# {"ok": true, "old_fingerprint": "abc123…", "new_fingerprint": "def456…",
#  "secrets_re_encrypted": 11, ...}

# 2. Re-escrow the new key
op document edit "ABS Production Vault Master Key" \
    /opt/abs/infra/vault-key/age.txt \
    --vault "ABS Production"

# 3. ROTATE every secret in the vault that the leaked key could decrypt:
#    - Stripe live secret key (Dashboard → API keys → Roll secret)
#    - Stripe webhook secret (Dashboard → Webhooks → Roll signing secret)
#    - Anthropic / OpenAI / Cohere / Groq API keys
#    - Discord webhook URL
#    - SMTP credentials
docker compose exec backend python -c "
from app.smart_link.vault_secrets import rotate_secret
rotate_secret(key_name='stripe_secret_key', provider='stripe', new_value='<NEW_VALUE>')
"
```

**Verification**

```bash
# Audit chain integrity
curl -fsS https://abs.your-domain.com/v1/admin/vault/audit \
  -H "Authorization: Bearer $ABS_ADMIN_TOKEN" | jq '.audit_chain_integrity'
# Expect "ok"

# Health endpoint
curl -fsS https://abs.your-domain.com/v1/status | jq '.overall'
```

**Post-mortem checklist**

- File a public security advisory if customer data was at risk.
- Update SECURITY.md disclosure timeline.
- Run a `git secrets` scan on all repositories.
- Add CI lint to block age key files in commits.

---

## Scenario 3 — Vault file corrupted

**Symptom**

```bash
docker compose exec backend sops -d /app/data/secrets.yaml
# Error: yaml: did not find expected node content
```

**Precheck**

```bash
# Check Docker volume snapshots, S3 backups, or nightly tarballs
ls -la /var/backups/abs/secrets-*.yaml
# Most recent backup tells you the maximum data loss window.
```

**Recovery**

```bash
# 1. Move corrupted file aside (DO NOT DELETE — forensic value)
mv /opt/abs/data/secrets.yaml /opt/abs/data/secrets.yaml.corrupt

# 2. Restore the most recent backup
cp /var/backups/abs/secrets-2026-04-26.yaml /opt/abs/data/secrets.yaml

# 3. Verify decrypts
docker compose exec backend sops -d /app/data/secrets.yaml | head -3

# 4. Restart backend
docker compose restart backend
```

**Verification**

```bash
curl -fsS https://abs.your-domain.com/v1/health/full | jq '.checks'
docker compose exec backend python -c "
from app.smart_link.vault_secrets import list_secrets
print(len(list_secrets()))
"
```

**Post-mortem checklist**

- Identify what caused corruption (disk full, kernel panic, faulty Docker volume driver).
- Verify backup cron is running (`crontab -l` on host).
- Increase backup retention if the corruption window was longer than the
  recovery point objective (RPO).

---

## Scenario 4 — Partial secret corruption

**Symptom**

`stripe_webhook_secret` returns `b64:...` while every other secret returns the
expected value. This usually means a fallback path was hit during a previous
encrypt and the row was never re-encrypted with sops.

**Recovery**

```bash
# 1. Identify the affected key
docker compose exec backend python -c "
from app.smart_link.vault_secrets import list_secrets, decrypt_secret
for r in list_secrets():
    pt = decrypt_secret(r['key_name'])
    print(r['key_name'], '->', pt[:8] if pt else 'EMPTY')
"

# 2. Re-encrypt that single secret with the production key
docker compose exec backend python -c "
from app.smart_link.vault_secrets import rotate_secret
rotate_secret(
    key_name='stripe_webhook_secret',
    provider='stripe',
    new_value='whsec_NEW_VALUE',
)
"

# 3. Confirm the row is now sops-encrypted (not 'b64:' prefixed) by inspecting
# the decrypted secrets file
docker compose exec backend sops -d /app/data/secrets.yaml | grep stripe_webhook_secret
```

**Verification**

```bash
# Run the validators
curl -X POST https://abs.your-domain.com/v1/smart-link/api-key \
  -H "Content-Type: application/json" \
  -d '{"provider":"stripe","api_key":"<NEW_VALUE>"}'

# Audit chain
curl -fsS https://abs.your-domain.com/v1/admin/vault/audit \
  -H "Authorization: Bearer $ABS_ADMIN_TOKEN" | jq '.recent[0]'
```

**Post-mortem checklist**

- Why did one secret end up in fallback mode? (sops binary missing on a host?)
- Add a startup assertion that no `b64:` prefix exists in production.
- Configure `ABS_VAULT_REQUIRE_SOPS=true` so the failure surface is loud, not silent.

---

## Appendix: precondition checklists

### Before declaring recovery complete

- [ ] `docker compose ps` shows all services healthy
- [ ] `/v1/health/full` returns `overall: ok`
- [ ] `/v1/admin/vault/audit` returns `audit_chain_integrity: ok`
- [ ] At least one MCP tool round-trips successfully (e.g., `system_status`)
- [ ] Stripe webhook test event delivers and your idempotency table records it
- [ ] Email send test (license refund template) lands in your inbox
- [ ] Escrow snapshot updated (date stamp visible in 1Password / S3 / vault store)

### Common pitfalls

- **Backups encrypted with the OLD key are useless after rotation.** Re-encrypt
  backups immediately after every rotation.
- **`sops --decrypt` writes to stdout.** Never pipe to `> /tmp/file` on a shared
  host — that file is plaintext.
- **The HMAC chain seals the audit log, not the secrets.** Tamper detection
  requires the audit log to be readable; if the database is wiped, you lose
  history but not secrets.

### Useful one-liners

```bash
# Last 5 audit entries
sqlite3 /opt/abs/data/abs.db \
    "SELECT ts, action, target_key FROM vault_audit_entries ORDER BY id DESC LIMIT 5"

# Verify integrity inline
docker compose exec backend python -c \
    "from app.vault.audit_chain import verify_chain; print(verify_chain())"

# Rotation dry-run preview (no actual rotate)
docker compose exec backend python -c \
    "from app.vault.audit_chain import stats; print(stats(window_hours=720))"
```

---

For incidents that do not match any of the four scenarios above, file a private
issue tagged `incident` and contact `security@automatiabcn.com`.
