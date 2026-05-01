> ⚠️ **DRAFT — LEGAL REVIEW REQUIRED**
> This document is a template provided as-is. Before signing with customers, qualified legal counsel review is mandatory. Automatia BCN takes no liability for unreviewed use. See `docs/legal/README.md` for review checklist.

# Automatia ABS – GDPR Data Retention Policy  

*Version 1.0 – Effective 27 April 2026*  

---

## 1. Overview  

Automatia ABS (the "Platform") is an AI‑orchestration solution that runs **exclusively on the customer's own infrastructure**. The core runtime, configuration files, and any data processed by the Platform remain under the full control of the customer's environment.  

Automatia ABS BCN (Barcelona, Spain) provides **cloud‑based ancillary services** that are required for the Platform to operate at scale:

| Service | Where it is hosted | What data is stored |
|---------|-------------------|---------------------|
| **Licensing & subscription management** | SaaS backend in the EU (AWS/Azure) | License metadata (customer ID, JWT, tier, seat count, org name) |
| **Billing** | Stripe (EU‑hosted) | Payment identifiers, invoices, billing email addresses |
| **Software updates** | CDN (EU edge) | Version identifiers, checksum metadata |
| **Optional LLM provider cascading** | Direct API calls from the customer's on‑premise node to third‑party LLM providers (Groq, Anthropic, Google, Cloudflare, Cohere, OpenRouter) | No personal data is stored by Automatia; only transient request IDs for troubleshooting |
| **Operational support** | Email (SMTP) and webhook endpoints | Email queue logs, webhook event payloads, consent records |

All personal data that **leaves the customer premises** is therefore limited to **licensing metadata, billing information, audit logs, webhook events, email delivery logs, consent records, and encrypted secrets**. The Platform itself never stores raw user‑generated content, model prompts, or inference results unless the customer explicitly configures a persistent store, which then falls outside the scope of this policy.

The policy below details the categories of personal data we hold, the retention periods applied to each, the technical and organisational measures that enforce those periods, and the rights that data subjects (or their authorised representatives) enjoy under the EU General Data Protection Regulation (GDPR) (Regulation (EU) 2016/679).

---

## 2. Categories of Data We Hold  

| # | Data Category | Concrete Examples | Legal Basis |
|---|---------------|-------------------|-------------|
| 1 | **License metadata** | • Customer‑assigned UUID (e.g., `c9f8a1‑…`)  <br>• Signed license JWT containing `sub`, `exp`, `tier`, `seats`  <br>• Organisation name, primary contact email, billing address | Contract performance (Art. 6(1)(b)) |
| 2 | **Audit logs** | • API request timestamps, endpoint, caller IP <br>• JWT validation outcomes (success/failure) <br>• MCP (Model‑Control‑Plane) tool invocations, parameters, result codes | Legitimate interests (Art. 6(1)(f)) – to provide security, debugging and compliance evidence |
| 3 | **Webhook events** | • Stripe `invoice.payment_succeeded` payloads (invoice ID, amount, currency) <br>• Provider status callbacks (e.g., LLM quota exhausted) | Contract & legitimate interests – needed for billing reconciliation and service health |
| 4 | **Email queue / delivery logs** | • Outbound email IDs, recipient address, subject line (e.g., "Your license key") <br>• Delivery status (sent, bounced, opened) | Contract (provision of account‑related communications) |
| 5 | **Consent records** | • Marketing opt‑in flag (`true/false`) with timestamp <br>• Feature‑flag opt‑in for telemetry (e.g., usage statistics) <br>• Record of data‑subject consent withdrawal | Consent (Art. 6(1)(a)) |
| 6 | **Encrypted secrets** | • Stripe secret key, webhook signing secret <br>• API keys for Anthropic, Groq, etc. <br>• SMTP credentials for outbound mail | Contract (necessary for service provision) – stored **encrypted at rest** using **SOPS/AGE** and never transmitted to the on‑premise ABS runtime |

> **Note:** All categories are stored in the **EU‑hosted PostgreSQL cluster** managed by Automatia ABS BCN, with backups replicated within the EU. Access is restricted to a minimal set of privileged engineers and is logged.

---

## 3. Retention Periods  

| Data Category | Retention Period | Rationale |
|---------------|------------------|---------  |
| **License metadata** | **365 days after the license expires** | Allows customers to renew, audit historical usage, and provides a safety window for dispute resolution. |
| **Audit logs** | **90 days** | Sufficient for operational troubleshooting, security incident investigation, and compliance audits while minimising data exposure. |
| **Webhook events** | **30 days** | Needed to verify payment status and provider callbacks; after 30 days the information is no longer required for reconciliation. |
| **Email queue / delivery logs** | **7 days** | Short‑term storage for delivery verification and bounce handling; after 7 days the logs become redundant. |
| **Consent records** | **Until the data subject withdraws consent or the associated processing ceases** (whichever is later) | GDPR requires retention only as long as the consent is valid and the processing purpose exists. |
| **Encrypted secrets** | **Indefinitely while the customer maintains an active subscription**; deleted immediately upon account termination. | Secrets are required for ongoing service operation; they are destroyed securely when no longer needed. |
| **Deleted‑account data** | **30‑day grace period** after the customer initiates deletion, then **permanent purge** | Provides a buffer for accidental deletions and satisfies the right to erasure. |
| **Data‑export downloads** (via `/v1/me/data-export`) | **24 hours** after the download link is generated | Limits exposure of exported personal data while giving the data subject sufficient time to retrieve it. |

All retention periods are **hard‑coded** in the Platform's back‑end and are not configurable by customers, ensuring uniform compliance across all deployments.

---

## 4. How Retention Is Enforced  

### 4.1 Automated Purge Jobs  

| Cron script | Frequency | Scope | Key actions |
|-------------|-----------|-------|-------------|
| `purge_license_metadata.py` | Daily at 02:00 UTC | License metadata older than 365 days post‑expiry | Deletes rows, logs IDs, triggers PostgreSQL `ON DELETE` cascade for related audit entries |
| `purge_audit_logs.py` | Hourly | Audit entries older than 90 days | Batch deletes in 10 000‑row chunks, writes audit‑purge log to immutable S3 bucket |
| `purge_webhook_events.py` | Every 6 hours | Webhook payloads older than 30 days | Removes JSON blobs, clears associated Stripe receipt IDs |
| `purge_email_logs.py` | Daily at 03:30 UTC | Email queue entries older than 7 days | Deletes from `email_queue` table, archives bounce codes for 30 days in a separate table |
| `purge_deleted_accounts.py` | Daily at 04:00 UTC | All data linked to accounts flagged `deleted_at` > 30 days | Executes full cascade delete, overwrites physical storage blocks using PostgreSQL `pg_repack` with `ZERO` fill‑mode |
| `purge_consent_records.py` | Weekly on Sundays | Consent entries where `withdrawn_at` is not null and older than 180 days | Removes withdrawn consent rows, retains minimal audit trail (ID, timestamp) for 180 days |

Each script runs inside a **dedicated Kubernetes Job** with the least‑privilege service account. Failure triggers an alert to the Security Operations Center (SOC) via PagerDuty.

### 4.2 Database Constraints & Triggers  

* **Foreign‑key cascades** ensure that when a license record is removed, all dependent audit logs are automatically purged.  
* **`BEFORE DELETE` triggers** on the `secrets` table invoke the `pgcrypto` `pgp_sym_decrypt` function to verify that the secret is encrypted before removal, preventing accidental plaintext leakage.  
* **Row‑level security (RLS)** policies restrict access to personal data to the `retention_service` role only.

### 4.3 Secure Deletion  

* For **soft‑deleted** rows (e.g., during the 30‑day grace period) we set a `deleted_at` timestamp and hide the rows from all queries via RLS.  
* Upon final purge, we use **PostgreSQL's `VACUUM FULL`** combined with **disk‑level shredding** (Linux `shred` on the underlying EBS volumes) to overwrite the physical blocks at least three times, satisfying the "secure erasure" requirement of GDPR Recital 153.  
* Backups that contain deleted data are **pruned** during the regular backup rotation (weekly full, daily incremental) and are also subject to the same retention limits.

### 4.4 Monitoring & Auditing  

* All purge activities are logged to an **append‑only, tamper‑evident audit log** stored in an immutable S3 bucket with Object Lock (Compliance mode).  
* Quarterly internal audits verify that the actual data present in the production database matches the retention schedule. Findings are reported to the Data Protection Officer (DPO).

---

## 5. Customer Data Rights  

Automatia ABS BCN recognises the full spectrum of GDPR data‑subject rights. The Platform provides **self‑service endpoints** that customers (or authorised representatives) can use to exercise those rights for the data that resides in the cloud component of the service.

| Right | How to Exercise | Technical Implementation |
|------|-----------------|-----------------------------|
| **Right of Access** (Article 15) | `GET /v1/me/data-export` (authenticated with the customer's API token) | Generates a **JSON** export of all personal data held (license metadata, audit logs, consent records). The file is stored temporarily in a signed URL valid for **24 hours**. |
| **Right to Rectification** (Article 16) | `PATCH /v1/me/account` with JSON body containing fields to update (e.g., `contact_email`, `org_name`) | Updates are written to the `customers` table; changes are logged with a `revision_id`. |
| **Right to Erasure** (Article 17) | `DELETE /v1/me/account` (requires multi‑factor confirmation) | Flags the account as `deleted_at = now()`. All associated data enters the 30‑day grace period before the automated purge runs. |
| **Right to Restriction of Processing** (Article 18) | `POST /v1/me/restrict` (sets a `processing_restricted` flag) | While the flag is true, no outbound emails, webhook deliveries, or telemetry are sent. |
| **Right to Data Portability** (Article 20) | `GET /v1/me/data-export?format=csv` | Returns the same data set as the access export but in **CSV** format, with column headers matching the JSON keys. |
| **Right to Object** (Article 21) | `POST /v1/me/objection` (specify processing purpose) | Records the objection in the `objections` table; subsequent processing for the specified purpose is halted. |
| **Right to Withdraw Consent** (Article 7) | Via the customer portal UI or `PATCH /v1/me/consent` | Updates the consent record's `withdrawn_at` timestamp; the system stops any processing that relies on that consent. |

All endpoints enforce **strong authentication** (OAuth 2.0 bearer tokens scoped to `profile:read/write`) and **audit logging** of the requestor's identity, timestamp, and outcome. Responses are rate‑limited to prevent abuse.

---

## 6. Contact Information  

If you have any questions, concerns, or requests regarding the processing of your personal data, please contact our Data Protection Officer:

**Data Protection Officer**  
Automatia ABS BCN  
Email: **privacy@automatiabcn.com**  
Phone: +34 93 123 4567  
Postal address: Carrer de Balmes, 12, 08007 Barcelona, Spain  

Our DPO will acknowledge receipt of any request within **48 hours** and will provide a substantive response no later than **30 days**, unless an extension is justified under GDPR Article 12(3).

---

## 7. Review & Amendments  

This policy is reviewed **annually** or whenever a material change to the Platform's data processing activities occurs (e.g., introduction of a new LLM provider, change of hosting region). All revisions are approved by the DPO and the Board of Directors.

---

> **This is a template — review with qualified legal counsel before adoption.**
