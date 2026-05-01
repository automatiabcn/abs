# Crisis Comm Playbook

Three runbooks for high-urgency, high-impact scenarios. Goal: rapid detection, clear comms, structured escalation.

**Single source of truth:** `https://status.abs-server.example.com`. Everything else (Twitter, blog, email) links here.

---

## Runbook 1 — Severe Production Outage

**Definition:** any prod 5xx rate > 5 % for ≥ 5 min, or full unreachability.

**Detection signal:** PagerDuty alert from Grafana (`PROD - API 5xx rate high`), or status-page synthetic probe failing 3 times in a row.

**First 15 minutes:**

1. On-call: ack PagerDuty.
2. On-call: declare SEV-1 in `#incidents` Slack.
3. On-call: open video war-room.
4. Founder: flip status page to "Investigating".

**Comms channel + draft:**

- Status page (initial): *"Investigating — we are looking into reports of increased API errors. Next update within 15 min."*
- Twitter `@abs_server_status`: same wording, link to status page.
- Update every 15 min, even if no news. Be factual, not speculative. Never say "fixed" before two consecutive green probes.

**Escalation tree:**

1. On-call engineer (paged automatically)
2. Founder
3. Legal counsel (if customer data is implicated)
4. CEO

**Post-mortem cadence:**

- 24 h public: blog post summarising impact + initial remediation, linked from status page.
- 72 h internal: full RCA, action items, owner per item.

---

## Runbook 2 — Security Disclosure

**Definition:** credible report of a critical vulnerability or zero-day, typically arriving at `security@abs-server.example.com`.

**Detection signal:** email to `security@` (PGP-encrypted) — alias pages on-call security lead.

**First 15 minutes:**

1. On-call: acknowledge with non-committal "Thank you, we are investigating". No technical details in reply.
2. On-call: create private channel `#security-incident-YYYY-MM-DD`, invite founders.
3. Team: validate reproducibly on a non-production system.
4. **Do not** discuss specifics in public channels.

**Comms channel + draft:**

- Direct email to reporter (when patch + advisory ready).
- Public blog + email to all users when a patch is available and customer action is needed.
- Draft (when patched): *"Security update for ABS Server `vX.Y.Z` — patch released for a critical vulnerability. Self-hosted users: update immediately. Managed cloud: already patched. Details and mitigation steps: [link]."*

**Escalation tree:**

1. On-call security lead
2. Founder
3. Legal counsel (CVE coordination, customer notification language)
4. CEO

**Post-mortem cadence:**

- 24 h public: CVE requested, blog post with vulnerability description (no exploit specifics), affected versions, fix.
- 72 h internal: RCA — how it got introduced, what catches it next time, regression test added.

---

## Runbook 3 — Social-Media Controversy

**Definition:** a high-engagement, factually wrong, or genuinely critical post about ABS gains traction on Hacker News, Twitter, or Reddit.

**Detection signal:** manual monitoring during launch (assigned rotation), or @-mention spike alert.

**First 15 minutes:**

1. Founder: surface the thread in `#launch` Slack with a link.
2. Team: read the entire thread before responding.
3. Team: draft a single unified response.
4. **Do not** engage individually or emotionally. Sleep on it if needed; one careful reply beats five impulsive ones.

**Comms channel + draft strategy:**

- Reply on the platform where the controversy lives.
- Acknowledge → "Thanks for the question / feedback."
- Correct (if misinformation) → "There seems to be a misunderstanding. Here's how X actually works…" + link to docs.
- Concede (if criticism is valid) → "Fair point. We made that tradeoff because of Y; we're taking this seriously for the roadmap."
- Stay factual. Avoid emotion. Concise + respectful.

**Escalation tree:**

1. Founder
2. CEO (only if the response could carry legal or major brand implications)

**Post-mortem cadence:**

- 24 h public: if the misunderstanding is widespread, a clarifying blog post.
- 72 h internal: discuss in launch retro — was the criticism valid? Does it require product or messaging change?
