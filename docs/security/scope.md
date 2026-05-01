# ABS External Pen-Test — Scope of Engagement

## Targets

| Component | Endpoint / URL | Notes |
|-----------|----------------|-------|
| Staging API | `https://staging.abs-server.example.com` | Full FastAPI stack, multi-tenant routing under `/v1/*`. |
| OAuth 2.1 Server | `https://staging.abs-server.example.com/oauth/authorize`, `/oauth/token`, `/.well-known/openid-configuration`, `/.well-known/jwks.json` | PKCE-enabled, RS256, JWKS rotation. |
| MCP Gateway | `https://staging.abs-server.example.com/v1/*` | All micro-service endpoints behind Cerbos PDP. |
| RAG Service | `https://staging.abs-server.example.com/v1/rag/ingest`, `/v1/rag/query` | Qdrant vector store + LLM inference. |
| Customer Portal | `https://portal.abs-server.example.com` | React SPA, same OAuth tokens. |

## In-Scope Test Categories

- **OWASP Top 10 (2021)** — full coverage on the web surface.
- **OAuth 2.1 / OIDC** — token replay, audience confusion, PKCE downgrade, JWKS cache poisoning, refresh-token theft.
- **RAG / LLM specific** — prompt injection, indirect (poisoned doc) injection, tool-use RCE, model jailbreak (DAN), cross-tenant retrieval, embedding poisoning, faithfulness regression.
- **Cerbos policy bypass** — pre-Qdrant gate evasion, attribute spoof, policy-file tamper.
- **Audit chain tamper** — S3-stored HMAC log replay/modification.
- **Tenant isolation** — slug-confusion, header injection, SQL injection at tenant boundary.

## Out of Scope

- Third-party SaaS infrastructure (managed Postgres, Redis, external LLM provider, Stripe).
- Social engineering of ABS employees, customers, or vendors.
- DoS / availability attacks (including rate-limit stress).
- Physical security and supply-chain (covered by separate program).

## Authorization

A signed engagement letter from the customer's legal team is required before any testing. The letter must reference the exact target URLs and the test windows. Production is *never* in scope without a separate amendment.

## Reporting

- Findings encrypted with the PGP key `security@abs-server.example.com`.
- Single channel: password-protected ZIP to that address.
- No public disclosure prior to written consent.

## Severity Mapping (CVSS v3.1)

| Severity | CVSS Range |
|----------|------------|
| Critical | 9.0 – 10.0 |
| High     | 7.0 – 8.9 |
| Medium   | 4.0 – 6.9 |
| Low      | < 4.0 |

## Acceptance Criteria for GA Release

- **Critical:** 0 findings.
- **High:** 0 findings.
- **Medium:** fewer than 5; each must be either remediated or carry a documented risk acceptance.
