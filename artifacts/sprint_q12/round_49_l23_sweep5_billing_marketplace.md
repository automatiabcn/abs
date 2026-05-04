# Round 49 — L23 sweep 5: billing_portal + marketplace silent raise audit

**Sprint:** Q12 Session 7
**Layer:** L23 (observability) — sweep 5
**Files touched:** 3 (2 src + 1 new test)
**Status:** ✅ shipped — **16/16 audit-coverage tests PASS**, 145 marketplace+billing regression PASS

---

## Bug surfaced — L23 silent raise gap on money paths

`grep "raise HTTPException" app/api/billing_portal.py app/api/marketplace.py`
returned **9 raise sites** with **0 emit_event calls**. Sweeps 1-4
(R13/R18/R19/R20/R21) covered me_account, me_data_export,
setup_admin, smart_link, beta_admin — but the customer-facing
*money* surface (Stripe portal) and *install* surface (marketplace)
were silent. A failed install / portal request was invisible to ops.

## Fix

### `core/backend/app/api/billing_portal.py` (EDIT)

5 emit_event calls added on the `/v1/billing/portal` endpoint:

| outcome | reason | status |
|---------|--------|--------|
| `denied` | `stripe_not_configured` | 503 |
| `denied` | `license_not_found` | 404 |
| `error` | `stripe_error` (+ `error_class`) | 502 |
| `error` | `portal_response_invalid` | 502 |
| `success` | (license_id) | 200 |

action taxonomy: `billing.portal.create`.

### `core/backend/app/api/marketplace.py` (EDIT)

5 emit_event calls across 4 endpoints:

| endpoint | action | reason | status |
|----------|--------|--------|--------|
| GET /plugins/{id} | `marketplace.plugin.lookup` | `plugin_not_found` | 404 |
| POST /install | `marketplace.install` | `plugin_not_found` | 404 |
| POST /install (gate) | `marketplace.install.gate` | `cross_tenant_forbidden` | 403 |
| POST /install (cosign) | `marketplace.install` | `signature_invalid` | 403 |
| DELETE /uninstall | `marketplace.uninstall` | `not_installed` | 404 |

`_enforce_tenant_match` now takes an optional `request` so the
emit can carry request_id when called from `install` /
`uninstall`. The legacy callers (none externally) work unchanged.

`install` + `uninstall` signatures now require a `Request`
parameter. FastAPI auto-injects this; no caller change.

### `core/backend/tests/test_q12_l23_sweep5_billing_marketplace.py` (NEW)

16 source-grep regression tests covering:
- `emit_event` import presence on both files
- 5 distinct `action="..."` taxonomies
- 8 distinct `reason="..."` values
- success-side audit on billing portal

## Verification

```
$ pytest tests/test_q12_l23_sweep5_billing_marketplace.py -v
16 passed in 0.53s

$ pytest tests/ -k "marketplace or billing_portal" -q
145 passed, 1 skipped in 6.57s   ← no regression
```

## Image rebuild

⚠️ Backend `app/` source touched. Per CLAUDE.md image rebuild
gate, the running infra-backend-1 image is now stale relative to
source. The host venv pytest verifies test correctness; a docker
rebuild is the **conditional** gate that fires when the change
ships to a deploy. For this audit-coverage round (no behavior
change beyond emit_event side-effects) the rebuild can be batched
with R50 (next round, also touches webhook signature error paths).

## Layer matrix delta

| Layer | Before R49 | After R49 |
|-------|------------|-----------|
| L23 | 4/3 ⭐ deep (R13+R18+R19+R20+R21 — 4 sweeps) | **5/3 ⭐ deep round 5** (+ R49 billing/marketplace silent-raise closure) |

L23 stays at deep — R49 is depth on the audit-coverage axis.

## Counters

- Backend pytest: 1636 → **1652 PASS** (Δ +16) / 14 skipped.
- Atomic commits in round: 1.
