# ABS Security Documentation Bundle

Welcome to the security audit repository for the ABS Server (FastAPI + OAuth 2.1 + Cerbos PDP + RAG + multi-tenant). This bundle is the entry point for external auditors, bug-bounty hunters, and the internal security team.

## Documents

- [Scope of Engagement](scope.md) — targets, in-scope categories, GA acceptance criteria.
- [OWASP + RAG Checklist](owasp_rag_checklist.md) — detailed test matrix.
- [OAuth Pen-Test Runbook](oauth_pentest.md) — step-by-step procedures and tooling.
- [HackerOne Program Brief](hackerone_program.md) — public bounty guidelines and tiers.

## CI / Automation

- Nightly scans: `.github/workflows/security-nightly.yml` (semgrep, trivy, gitleaks, syft SBOM).
- OAuth pen-test scripts: `security_tests/oauth/`.

## Contact

- Encrypted reports → `security@abs-server.example.com` (PGP key on the public security page).
- Triage SLA: 24 h for critical, 5 business days for medium/low.
