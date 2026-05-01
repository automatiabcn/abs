# Admin Dashboard — Operator Guide  

*Automatia BCN Self‑host AI Orchestration (ABS)*  

---  

## 1. Login & IP Whitelist Setup  

| Variable | Purpose | Typical Value |
|----------|---------|---|
| `ABS_ADMIN_PASSWORD_HASH` | Bcrypt‑hashed admin password (used for basic auth) | `$(htpasswd -bnBC 12 "" yourpw \| cut -d: -f2)` |
| `ABS_ADMIN_JWT_SECRET` | HMAC secret for signing admin JWTs | 32‑byte base64 string |
| `ABS_ADMIN_IP_WHITELIST` | Comma‑separated list of CIDR blocks allowed to reach `/admin` | `10.0.0.0/8,192.168.1.0/24` |

### 1.1 Generate a bcrypt hash  

```bash
# Replace `yourpw` with the desired password
htpasswd -bnBC 12 "" yourpw | cut -d: -f2
# Example output:
$2y$12$K9e9vZcJxGZp6vZcYhVhUe5KpY9U2Zc6hG9QeV6u8YcZc5fGzQe2W
```

Copy the resulting string into `ABS_ADMIN_PASSWORD_HASH`.  

### 1.2 JWT configuration  

- Tokens are issued with a **TTL of 24 h**.  
- The server returns the token in two ways:  

  1. **Bearer header** – `Authorization: Bearer <jwt>` for API clients.  
  2. **HTTP‑only cookie** – `Set-Cookie: abs_admin_jwt=<jwt>; HttpOnly; Secure; SameSite=Strict; Max-Age=86400` for the web UI.  

If the token expires, the UI forces a re‑login; the admin password is verified against the bcrypt hash.  

### 1.3 IP whitelist enforcement  

The middleware checks `ABS_ADMIN_IP_WHITELIST` before any authentication step. Requests from non‑listed CIDRs receive **403 Forbidden**. Update the env var and restart the container to apply changes.  

---  

## 2. Dashboard Widgets Explained  

| Widget | What it Shows | Data Source | Color Meaning |
|--------|---------------|-------------|---|
| **Revenue** | Daily/weekly gross USD, net after refunds, MRR trend | `billing.revenue` table (Stripe sync) | **Green** = growth > 5 % week‑over‑week; **Yellow** = 0 %–5 %; **Red** = decline > 5 % |
| **Licenses** | Active, expired, revoked counts; per‑plan breakdown | `license` service DB | **Blue** = healthy (≤ 2 % revocation); **Orange** = revocation spike |
| **Security Score** | Composite score (0‑100) from static analysis, runtime audit, CVE exposure | `security_audit` microservice | **≥ 80** = green; **60‑79** = amber; **< 60** = red |
| **Compliance** | GDPR/PCI‑DSS status flags, last audit timestamp | `compliance` module | **Green** = all checks pass; **Red** = any failure |
| **Beta Funnel** | # of beta requests, pending approvals, conversion to paid | `beta_queue` table | **Purple** = pending; **Green** = conversion > 20 % |
| **Recent Errors** | Last 20 error logs (timestamp, endpoint, error code) | Centralised log store (`ELK` index `abs-errors`) | **Red** = critical (5xx); **Yellow** = warning (4xx) |

All widgets refresh every 60 seconds; manual refresh is available via the top‑right reload icon.  

---  

## 3. Daily Operational Checklist  

1. **Dashboard health check** – Verify all widgets display green/amber; note any red alerts.  
2. **Beta queue review** – Open **Beta Funnel** → approve or reject pending requests (see §5.3).  
3. **Error scan** – Open **Recent Errors**, filter for `level:critical`. Investigate any new 5xx entries; create a ticket if unresolved.  
4. **Compliance status** – Confirm the **Compliance** widget shows green. If red, open the compliance console and address the failing check.  
5. **Churn flags** – Run `curl -H "Authorization: Bearer $TOKEN" https://abs.internal/v1/admin/churn/flags` and review any accounts flagged for imminent cancellation.  

---  

## 4. Weekly Checklist  

| Item | Action | Command / UI |
|------|--------|---|
| **Revenue trend** | Export weekly revenue CSV, compare to prior week, note anomalies > 10 % | `abs-cli revenue export --week=$(date -d 'last week' +%Y-%U) > rev.csv` |
| **Security audit** | Pull latest `security_audit` JSON, verify score ≥ 80, check new CVEs | `curl -H "Authorization: Bearer $TOKEN" https://abs.internal/v1/admin/security_audit` |
| **Vault rotation** | Confirm `vault` key rotation date is within 30 days; rotate if overdue | `abs-cli vault rotate --force` |
| **Beta‑to‑paid conversion** | Calculate conversion rate from beta funnel data; aim ≥ 20 % | `abs-cli beta conversion --period=7d` |
| **Audit log spot‑check** | Randomly sample 100 audit log entries for tampering or missing fields | `abs-cli audit log --sample=100 --output=spotcheck.json` |

Document findings in the weekly ops log (e.g., Confluence page *ABS Weekly Ops*).  

---  

## 5. Common Tasks (Walk‑throughs)  

### 5.1 Revoke a License  

```bash
# 1. Obtain admin JWT (if not already)
TOKEN=$(abs-cli auth login --user admin --password yourpw --output token)

# 2. Identify the JTI (license token identifier) to revoke
curl -H "Authorization: Bearer $TOKEN" \
     https://abs.internal/v1/admin/license | jq '.licenses[] | select(.status=="active") | .jti'

# 3. Revoke
curl -X POST -H "Authorization: Bearer $TOKEN" \
     https://abs.internal/v1/admin/license/<jti>/revoke
```

The endpoint returns `200 OK` and the license status changes to **revoked**.  

### 5.2 Issue a Refund (Stripe)  

1. Log into the Stripe Dashboard → **Payments**.  
2. Locate the charge using the **Invoice ID** shown in the **Revenue** widget tooltip.  
3. Click **Refund** → select **Full** or **Partial** amount.  
4. Confirm.  

After the refund is processed, the **Revenue** widget updates within 5 minutes. No ABS‑side action required.  

### 5.3 Approve a Beta Request  

```bash
# List pending beta requests
curl -H "Authorization: Bearer $TOKEN" \
     https://abs.internal/v1/admin/beta?status=pending | jq '.requests[]'

# Approve a specific request (replace {id})
curl -X POST -H "Authorization: Bearer $TOKEN" \
     https://abs.internal/v1/admin/beta/<id>/approve
```

The response includes a newly generated license key. Communicate the key to the requester via the configured notification channel (email or Slack webhook).  

---  

## 6. Troubleshooting  

| Symptom | Likely Cause | Fix |
|---------|--------------|---|
| **403 Forbidden – IP not allowed** | Request originates from an IP outside `ABS_ADMIN_IP_WHITELIST`. | Add the CIDR to `ABS_ADMIN_IP_WHITELIST` and restart the container. |
| **401 Unauthorized – Invalid JWT** | Token expired or signed with wrong secret. | Regenerate admin JWT (`abs-cli auth login`) and ensure `ABS_ADMIN_JWT_SECRET` matches the secret used by the auth service. |
| **Dashboard widgets stuck on "Loading…"** | Centralised log store (`ELK`) unreachable or `billing` microservice down. | Verify connectivity: `curl http://elasticsearch:9200` and `systemctl status abs-billing`. Restart failing service. |
| **Beta approval returns 409 Conflict** | Same request already approved or license quota exhausted. | Query the beta request status (`/v1/admin/beta/{id}`) to confirm. If quota is the issue, increase `ABS_BETA_LICENSE_QUOTA` env var and reload. |

When a fix requires a container restart, use the standard deployment command:  

```bash
docker compose restart abs-admin
```

---  

Last updated: 2026-04-27
