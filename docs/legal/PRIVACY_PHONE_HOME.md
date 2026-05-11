# License Heartbeat Phone-Home — Privacy Notice

*Last updated: 2026-05-11*
Contact: **support@automatiabcn.com**

This document discloses exactly what data the customer-side Automatia ABS
backend transmits to Automatia BCN's license activation server, why it is
transmitted, where it is stored, and how to disable it.

---

## 1. What is sent

On every license heartbeat — by default once every 30 seconds on the
customer instance, throttled server-side to update the activation record
**at most once per hour** — the ABS backend sends:

| Field | Type | Purpose |
|-------|------|---------|
| `jti` | UUID | License JWT identifier — identifies the license, not the user |
| `machine_fp` | SHA-256 hex | Machine fingerprint (hash of host hardware identifiers) — **not** personally identifiable |
| `build_hash` | hex | Docker image commit SHA — confirms the customer is running a non-tampered image |
| `instance_url` | string | Customer's instance URL (e.g. `https://abs.example.com`) for fault correlation only |
| `version` | string | ABS release version (e.g. `1.0.0-rc11`) |

**No customer payload is sent.** Chat messages, RAG documents, prompts,
embeddings, API keys, OAuth tokens, user accounts, and any other tenant
data **never leave the customer's server** as part of the heartbeat.

The machine fingerprint is a one-way hash of stable hardware identifiers
(machine ID + primary MAC + product UUID where available). It cannot be
reversed to identify the customer's hardware, and it does not include any
personally identifiable information.

---

## 2. Why it is sent

The heartbeat exists for three narrow purposes:

1. **License activation accounting** — proves that the customer is the
   current owner of the license; supports the "one license, one machine"
   constraint of the Commercial License.
2. **Revocation propagation** — if a license is suspended (refund, policy
   violation, fraud), the next heartbeat receives a `revoked: true`
   response and the backend enters a 7-day grace window before refusing
   to start.
3. **Tamper detection** — the `build_hash` lets Automatia BCN detect when
   a customer is running a modified or rebuilt image (which would be a
   BUSL-1.1 production-use violation).

The heartbeat is **not** used for usage analytics, product telemetry,
A/B testing, or marketing.

---

## 3. Where it goes

- **Endpoint:** `https://abs-license-activation.automatiaabs.workers.dev/v1/heartbeat`
- **Carrier:** Cloudflare Workers (global edge), EU-region routing where
  Cloudflare's automatic geo-routing permits.
- **Transport:** HTTPS / TLS 1.3 only.
- **Authentication:** the request itself is signed with the license JWT;
  no separate credentials are transmitted.

---

## 4. What is stored

Server-side storage is in a Cloudflare Workers **KV namespace**
(`abs-license-state`), with the following properties:

- **Retention:** 90-day rolling TTL on each activation record. Records
  older than 90 days are auto-purged by Cloudflare.
- **Granularity:** one record per `jti`. Records are overwritten on each
  successful heartbeat — only the most recent state is retained.
- **No IP logging:** Cloudflare Worker code does not log the requesting
  IP address. Cloudflare's edge access logs (out of our control) follow
  Cloudflare's own retention policy.
- **No per-request audit log:** only aggregated activation counters and
  the latest state per license.

---

## 5. Lawful basis (GDPR / data protection)

The heartbeat contents (UUID + hardware hash + image SHA + URL + version)
do not constitute personal data under GDPR — they identify a software
installation, not a natural person.

If the customer's `instance_url` includes a personal name (e.g.
`https://abs.acme-jdoe.example.com`), and that name identifies a real
person, Automatia BCN's lawful basis for processing is **legitimate
interest** (Art. 6(1)(f) GDPR) — namely, enforcing the license terms
the customer agreed to at purchase.

A Data Processing Agreement (DPA) template is provided at
[docs/legal/dpa-template.md](dpa-template.md) for customers who require
one.

---

## 6. How to verify or disable

### Verify (recommended)

```bash
# On the customer host:
docker logs abs-backend-1 2>&1 | grep -i "heartbeat" | tail -20
```

You will see entries of the form `heartbeat OK build=… jti=…`. No payload
content is logged beyond the five fields described in Section 1.

### Disable

Set the following in `/opt/abs/.env` and restart the backend:

```bash
ABS_LICENSE_GATE_DISABLED=1
```

```bash
cd /opt/abs && docker compose up -d --force-recreate backend
```

**Consequences of disabling:**

- The software continues to run normally.
- Revocation propagation is lost — if Automatia BCN suspends your license
  (refund, policy violation), your instance will **not** receive the
  revocation signal and will keep operating until the next license renewal
  check.
- License-binding tamper detection is reduced.
- Your Commercial License terms still apply — disabling the heartbeat does
  not waive your obligations under the BUSL-1.1 or Commercial License.

---

## 7. Open-source equivalent

After the Change Date (**2030-05-07**), the software automatically
converts to Apache License 2.0. At that point:

- The heartbeat code path remains in the source tree.
- New deployments may safely disable it without any license consequence.
- Existing deployments at conversion time continue to function as before;
  the gate is fail-open after license expiry.

---

## 8. Updates to this notice

Automatia BCN may update this notice as the heartbeat implementation
evolves. The canonical version is always at:

`https://github.com/automatiabcn/abs/blob/main/docs/legal/PRIVACY_PHONE_HOME.md`

Material changes (new fields sent, retention extended, new endpoints)
will be announced via the customer mailing list at least 30 days before
they take effect.

---

See also:

- [LICENSE](../../LICENSE) — BUSL-1.1 license text
- [NOTICE.md](../../NOTICE.md) — canonical attribution + trademark statement
- [TRADEMARKS.md](TRADEMARKS.md) — trademark policy
- [privacy-policy.md](privacy-policy.md) — customer-facing privacy template
- [dpa-template.md](dpa-template.md) — Data Processing Agreement template
