# T-064 General Availability Launch Plan

This directory contains all documentation related to the T-064 GA launch for ABS Server. All activities are coordinated through the master checklist.

⚠️ **DO NOT POST WITHOUT FOUNDER APPROVAL** — Sprint 15-16 protocol gates all external launch actions on explicit sign-off recorded in the repo.

---

## Documents

- [GA Launch Checklist](ga-launch-checklist.md) — master plan: pre-flight, launch day timeline, post-launch.
- [Press Kit](press-kit.md) — official information for press and partners.
- [Launch Copy](launch-copy.md) — ready-to-paste copy for HN / Reddit / Twitter / Linear / Product Hunt.
- [Landing A/B Test](landing-ab-test.md) — `landing_hero_v1` plan with hypothesis, variants, sample size.
- [Crisis Comm Playbook](crisis-comm-playbook.md) — runbooks for outage, security disclosure, social controversy.

## GA Hard Gates Recap

Launch is contingent on every gate passing on T-1d:

- **T-058** Helm umbrella deployed to `abs-prod`.
- **T-059** 100 RPS @ p99 < 500 ms (two consecutive runs).
- **T-060** 0 critical / 0 high vulnerabilities; 7 consecutive clean nightly scans.
- **T-062** Latest DR drill records `rto_pass: true` and `smoke_ok: true`.

GO/NO-GO meeting on T-1d at 16:00 UTC; decision is recorded in the checklist.
