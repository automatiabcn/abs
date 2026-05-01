# T-064 GA Launch Checklist

This is the master checklist for the ABS Server General Availability launch. No step is skipped. All gates must be green for GO.

**Owners:** `@founder`, `@ops`

---

## Pre-Launch Phase (T-7d → T-1d)

### T-7d (EOD)
- [ ] **Finalize launch assets** — all copy, images, and videos final and approved. `[owner: @founder]`
- [ ] **Finalize press kit** — `press-kit.md` complete and reviewed. `[owner: @founder]`

### T-5d (EOD)
- [ ] **Deploy RC to staging** — Release candidate `v1.0.0` deployed to staging. `[owner: @ops]`
  - Verify: `kubectl get pods -n abs-staging | grep abs-backend-v1.0.0`

### T-3d (EOD)
- [ ] **Run staging hard-gate checks** — every gate below tested green on staging. `[owner: @ops]`

### T-2d (EOD)
- [ ] **Deploy RC to production (dark)** — `v1.0.0` deployed to prod, traffic still on previous version. `[owner: @ops]`
  - Verify: `kubectl get pods -n abs-prod | grep abs-backend-v1.0.0`

### T-1d (12:00 UTC) — Production hard-gate checks
- [ ] **T-058 Helm umbrella deployed** — `[owner: @ops]`
  - Verify: `helm status abs -n abs-prod | grep "STATUS: deployed"`
- [ ] **T-059 100 RPS p99 < 500ms (two consecutive runs)** — `[owner: @ops]`
  - Verify: re-run `.github/workflows/k6-weekly.yml` twice via dispatch; confirm both summaries report `http_req_duration p(99) < 500`.
- [ ] **T-060 0 critical / 0 high** — `[owner: @ops]`
  - Verify: latest `security-nightly` artifacts (`pip-audit.json`, `trivy-fs.json`, `gitleaks.json`) reviewed; SBOM diff clean.
- [ ] **T-062 DR drill `rto_pass=true`** — `[owner: @ops]`
  - Verify: `benchmarks/results/dr-YYYY-MM.json` shows `rto_pass: true` and `smoke_ok: true`.
- [ ] **Stripe webhook live** — `[owner: @founder]`
  - Verify: `stripe events list --live --limit 5` returns recent `checkout.session.completed`; webhook returns 200.
- [ ] **Status page live** — `[owner: @ops]`
  - Verify: `curl -fsS https://status.abs-server.example.com | grep -q "All Systems Operational"`.
- [ ] **Support auto-responder live** — `[owner: @founder]`
  - Verify: send test mail; auto-reply within 2 min.

### T-1d (16:00 UTC) — GO/NO-GO meeting
- [ ] All stakeholders present; decision recorded in this file. `[owner: @founder]`
  - Decision: `[ ] GO` `[ ] NO-GO` — initials + UTC timestamp.

---

## Launch Day (T-0, all times UTC)

- [ ] **08:00** — final systems check, dashboards green, war room open. `[owner: @ops]`
- [ ] **09:00** — post to Hacker News. `[owner: @founder]`
- [ ] **09:15** — founder first comment on HN. `[owner: @founder]`
- [ ] **10:00** — post to r/SaaS + r/selfhosted. `[owner: @founder]`
- [ ] **11:00** — Tweet 1/10 of the launch thread; schedule remainder every 15 min. `[owner: @founder]`
- [ ] **12:00** — publish Linear blog post. `[owner: @founder]`
- [ ] **13:00** — Product Hunt launch. `[owner: @founder]`
- [ ] **13:15** — first 3 maker comments on Product Hunt. `[owner: @founder]`
- [ ] **14:00 – 22:00** — active monitoring + engagement: comments, Stripe, Grafana, Sentry, support tickets.

---

## Post-Launch Phase (T+1d → T+7d)

- [ ] **T+1d** — "thank you" updates on Twitter and HN; share initial traction. `[owner: @founder]`
- [ ] **T+3d** — analyze A/B test (`landing_hero_v1`). If significant, promote winning variant. `[owner: @ops]`
- [ ] **T+7d** — publish launch retrospective on the blog + internal post-mortem. `[owner: @founder]`

---

## Honest failure modes

- HN front page goes negative — see `crisis-comm-playbook.md` Runbook 3.
- Stripe live mode rejects first transaction — fall back to test mode for 24 h while debugging webhook.
- Helm rollback needed — `helm rollback abs <prev-rev> -n abs-prod`; status page → "investigating".
