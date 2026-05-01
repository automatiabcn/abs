# ABS HackerOne Bug Bounty — Program Brief

## Program Type

Managed bug-bounty program operated by **ABS Security** through HackerOne.

## Scope

| Included Assets | Description |
|-----------------|-------------|
| Staging API | `https://staging.abs-server.example.com/v1/*` — all micro-service endpoints. |
| OAuth 2.1 Server | Authorization, token, JWKS, OIDC discovery endpoints. |
| RAG Service | `/v1/rag/ingest`, `/v1/rag/query`. |
| Customer Portal | React SPA at `portal.abs-server.example.com`. |

All testing must be against staging. Production is out-of-scope without prior written approval.

## Bounty Tiers

| Severity | Reward |
|----------|--------|
| Low (CVSS < 4.0) | $50 |
| Medium (4.0 – 6.9) | $500 |
| High (7.0 – 8.9) | $2,000 |
| Critical (9.0 – 10.0) | $10,000 |

**RAG-specific multipliers ×1.5** for findings in:

- Cross-tenant data leakage via RAG (Cerbos pre-Qdrant bypass).
- Prompt-injection enabling tool-use RCE.

## Hall of Fame

Top contributors listed on the ABS security page with a short, non-sensitive description.

## Safe Harbor

ABS authorizes good-faith research on the listed assets, provided researchers:

- Do not access, modify, or destroy data of other tenants.
- Do not launch DoS or exceed rate limits intentionally.
- Report findings within 30 days of discovery.

Good-faith research is exempt from CFAA / DMCA claims under this program.

## Disclosure Policy

- Coordinated 90-day window after the initial report.
- ABS provides a remediation timeline; if missed, the researcher may publish 14 days after notification.

## Out of Scope

- Rate-limit testing that triggers service degradation.
- Self-DoS via account lockout.
- Social engineering of ABS staff or customers.
- Attacks against third-party SaaS components (Stripe, Postgres host, external LLM provider).
- Findings without a clear security impact (best-practice misses, missing security headers on non-sensitive paths).
