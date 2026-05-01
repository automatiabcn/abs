# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Automatia ABS, please report it
**privately** before disclosing publicly:

- **Email:** [security@automatiabcn.com](mailto:security@automatiabcn.com)
- **PGP key:** available on request
- **Response time:** within 72 hours; critical issues within 24 hours

Please include:

1. A description of the vulnerability and its impact
2. Steps to reproduce (proof of concept welcome)
3. Affected version(s) — `git log --oneline -5` of the commit you tested
4. Optional: your suggested fix

## Supported Versions

| Version | Supported |
|---|:-:|
| `main` | ✅ |
| `0.1.x` | ✅ |
| `< 0.1` | ❌ |

We will patch the latest minor version for at least 12 months after each release.
Self-Host Lifetime customers receive update channel notifications for critical
patches.

## Disclosure Timeline

We follow a **90-day coordinated disclosure** policy:

1. **Day 0** — You report via email.
2. **Day 0–7** — We acknowledge, triage, and assign a severity.
3. **Day 7–60** — We develop and test a fix.
4. **Day 60–80** — We prepare release notes and credit you (unless you prefer
   anonymity).
5. **Day 80–90** — Public release + advisory; you may publish your write-up.

Severe vulnerabilities (RCE, auth bypass) may be expedited.

## Out of Scope

- Self-inflicted issues from misconfiguration (e.g. exposing the admin port).
- Issues in third-party providers (Stripe, Anthropic) — report to them directly.
- Social-engineering attacks against Automatia BCN staff.

## Hall of Fame

Contributors who report valid vulnerabilities will be credited in the release
notes (with their permission). For high-severity finds we may issue a paid
bounty — case by case.
