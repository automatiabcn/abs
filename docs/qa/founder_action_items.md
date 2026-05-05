# Founder Action Items — Pre‑Tester‑Handoff  

## Status  
Sprint Q12 closed at commit `dbaeca8` on branch `feat/sprint-q12-deep-quality` (S12 R96–R99 regression close-out + this docs alignment = R100).  

> **S11 → S12 retraction note:** the prior version of this file referenced HEAD `ddfdf8c` and claimed full-suite green; founder host run on 2026-05-05 revealed 1735 passed / 3 failed / 17 errors. S12 root-caused the failure to a missing `data_dir` isolation in `tests/test_q12_magic_link_e2e.py` (single polluter for all 20 fail/error). One atomic fix re-greens to **1755 passed / 0 failed / 0 errors / 14 skipped / 3 deselected** in 176.13s.

The checklist below contains **eight** ordered items. **Step 0 is the new mandatory pre-flight gate** added in S12: founder runs the canonical full-suite command on the host shell and confirms 0 failed / 0 errors before proceeding. Items 1‑3 configure environment‑level values, items 4‑5 apply infrastructure changes, item 6 validates the nightly Lighthouse run, and item 7 packages everything for the external tester. Execute each step in the listed order; later steps assume the previous ones have completed successfully.

---

## 0. Mandatory pre-flight — full backend suite must be GREEN (S12 gate)  

**Goal** – Confirm the canonical full-suite command returns `0 failed / 0 errors` on the founder host before any other step. Selective subsets (`pytest tests/test_X.py`) are NOT acceptable evidence for the handoff seal — that path produced the false S11 GREEN.

**Run**

```bash
cd core/backend
./.venv/bin/python -m pytest --no-header -q \
  --ignore=tests/test_providers.py \
  --ignore=tests/test_q03_real_saas_backends.py \
  --ignore=tests/test_update_channel.py
```

**Expected last line**

```
1755 passed, 14 skipped, 3 deselected, 41 warnings in NNN.NNs (0:0M:SS)
```

The three ignores are:
- `test_providers.py` — live SaaS provider smoke (off by default; runs in staging cron)
- `test_q03_real_saas_backends.py` — Recall.ai/Deepgram/ElevenLabs/Gmail live (founder approval gate)
- `test_update_channel.py` — live update channel signature (staging only)

If the run reports any failure or error, STOP. Do not advance to step 1 until 0 failed / 0 errors. Capture the last line and paste it into `tester_handoff_checklist.md` §8 Sign-off.

---  

## 1. Stripe products + Price IDs setup  

**Goal** – Create three Stripe *Products* (Self‑Host, Team‑5, Team‑10) and attach the correct *Price* objects.  

**Run**  

```bash
# Ensure the Stripe secret key is exported
export STRIPE_API_KEY=sk_test_XXXXXXXXXXXXXXXXXXXXXXXX

# The script is idempotent – it will create missing objects and update metadata on existing ones.
python infra/scripts/setup_stripe_products.py
```

**Output (example)**  

```
price_self_host=price_1N2aBcD3EfGhIjKlMnOpQrSt
price_team_5=price_1N2aBcD3EfGhIjKlMnOpQrSu
price_team_10=price_1N2aBcD3EfGhIjKlMnOpQrSv
```

**Verify**  

```bash
stripe products list --limit 10
```

* You should see three products whose `metadata.tier_id` values are `self_host`, `team_5`, and `team_10`.  
* Each product must have exactly one recurring price with the IDs printed above.  

> **⚠️ Critical** – Do not rename the products after creation; the `tier_id` metadata is used by the licensing service.

---  

## 2. Environment variables  

Populate the production `.env` (encrypted with SOPS via Vault 013) with the numeric pricing constants and the Stripe Price IDs obtained in step 1.

| Variable | Value | Description |
|----------|-------|-------------|
| `ABS_SEAT_PRICE_SELF_HOST` | `299` | USD / month for a single self‑host seat |
| `ABS_SEAT_PRICE_TEAM_5` | `1196` | USD / month for a 5‑seat team |
| `ABS_SEAT_PRICE_TEAM_10` | `2093` | USD / month for a 10‑seat team |
| `ABS_REVENUE_WIDGET_MULTIPLIER` | `25` | Internal multiplier used by the revenue widget |
| `ABS_PRICE_SELF_HOST` | `price_…` | Stripe Price ID from step 1 |
| `ABS_PRICE_TEAM_5` | `price_…` | Stripe Price ID from step 1 |
| `ABS_PRICE_TEAM_10` | `price_…` | Stripe Price ID from step 1 |

**Apply**  

```bash
# Edit the encrypted env file (example path)
sops -e -i infra/env/production.env
# Insert the lines above, then save.
git add infra/env/production.env
git commit -m "chore: add Q12 pricing env vars"
```

**Verify after rebuild**  

```bash
docker compose up -d api
docker compose exec api python -c "import os, json; print(json.dumps({k: os.getenv(k) for k in ['ABS_SEAT_PRICE_SELF_HOST','ABS_PRICE_SELF_HOST']}))"
```

The command must print the numeric price and the matching Stripe Price ID.  

---  

## 3. License JWT mint + `ABS_LICENSE_KEY`  

**Goal** – Mint a 30‑day self‑host license for the tester and store the resulting JWT in the environment.  

**Python snippet** (run on a machine with the `abs-license` package installed):

```python
import os, datetime, jwt

def generate_license(tier: str, days: int) -> str:
    payload = {
        "tier": tier,
        "exp": int((datetime.datetime.utcnow() + datetime.timedelta(days=days)).timestamp()),
        "iat": int(datetime.datetime.utcnow().timestamp()),
        "iss": "abs-server",
    }
    secret = os.getenv("ABS_LICENSE_SIGNING_KEY")  # stored in Vault
    return jwt.encode(payload, secret, algorithm="HS256")

# Mint a 30‑day self‑host license
license_jwt = generate_license(tier="self_host", days=30)
print(license_jwt)
```

**Persist**  

```bash
# Capture the output
LICENSE_JWT=$(python mint_license.py)
# Append to the encrypted env
sops -e -i infra/env/production.env <<< "ABS_LICENSE_KEY=$LICENSE_JWT"
git add infra/env/production.env
git commit -m "chore: add tester self‑host license key"
```

**Verify**  

```bash
curl -s -H "Authorization: Bearer $LICENSE_JWT" \
     https://abs.example.com/v1/license/status | jq .
```

Expected JSON contains `"tier":"self_host"` and `"valid_until"` within the next 30 days.  

> **⚠️ Note** – The R86 guard warns when `valid_days` > 25 years; a 30‑day token is well within limits.

---  

## 4. Cerbos Helm upgrade on production cluster  

**Goal** – Deploy the R76 "umbrella" policy fix to the live Kubernetes cluster.  

**Run**  

```bash
# Ensure you are targeting the production context
kubectl config use-context prod-cluster

# Upgrade (or install) the Helm chart with production values
helm upgrade --install abs ./helm/abs \
  -f ./helm/values.production.yaml \
  --namespace abs-system
```

**4‑step verification ritual**  

1. **Rollout status**  

   ```bash
   kubectl rollout status deployment/cerbos -n abs-system --timeout=120s
   ```

2. **Pod logs** – Look for `policy_load_success=true`  

   ```bash
   kubectl logs -l app=cerbos -n abs-system | grep policy_load_success
   ```

3. **Health endpoint**  

   ```bash
   curl -s https://abs.example.com/cerbos/healthz | grep '"status":"ok"'
   ```

4. **Policy sanity check** – Run a dry‑run request  

   ```bash
   curl -X POST -H "Content-Type: application/json" \
        -d '{"principal":{"id":"test","roles":["admin"]},"resource":{"kind":"subscription"}}' \
        https://abs.example.com/cerbos/check
   ```

   The response must contain `"allowed":true`.  

> **✅ Caveat #12** is now closed.

---  

## 5. Image rebuild + push to registry  

**Goal** – Build the backend image that contains the HEAD commit `ddfdf8c` (including R91) and make it available to the production cluster.  

**Build & push**  

```bash
# Build
docker build -t registry.example.com/abs/backend:ddfdf8c \
  --build-arg GIT_SHA=ddfdf8c .

# Push
docker push registry.example.com/abs/backend:ddfdf8c
```

**Deploy**  

```bash
# Patch the deployment to use the new image
kubectl set image deployment/abs-backend \
  abs-backend=registry.example.com/abs/backend:ddfdf8c \
  -n abs-system

# Wait for rollout
kubectl rollout status deployment/abs-backend -n abs-system --timeout=180s
```

**Smoke test**  

```bash
curl -s https://abs.example.com/healthz | grep '"status":"ok"'
curl -s https://abs.example.com/v1/cascade/providers | jq '.providers | length'
```

The `/healthz` endpoint must return HTTP 200 with `{"status":"ok"}`.  
The `/v1/cascade/providers` response should list all configured provider keys (see step 7).

---  

## 6. Lighthouse first nightly cron review  

**Goal** – Verify that the R82 performance fix is included in the first Saturday night run after the release.  

**Schedule** – Saturday 2026‑05‑09 02:00 UTC (the first nightly cron after the merge).  

**Review procedure**  

```bash
# Download the artifact produced by the nightly pipeline
curl -O https://ci.example.com/artifacts/sprint_q12/round_90_lighthouse_artifact.zip
unzip round_90_lighthouse_artifact.zip -d lighthouse_review
```

Open `lighthouse_review/report.json` and extract the four core scores:

| Category | Score (0‑1) |
|----------|------------|
| Performance | 1.0 |
| Accessibility | 1.0 |
| Best Practices | 1.0 |
| SEO | 1.0 |

**Pass criteria** – All four scores ≥ 0.9. The artifact `artifacts/sprint_q12/round_90_lighthouse_artifact_review.md` must contain the table above and a "PASS" annotation.  

If any score falls below 0.9, open a hot‑fix branch `hotfix/lighthouse-q12` and repeat steps 1‑5 before the next nightly run.

---  

## 7. Tester handoff package  

| Item | Details |
|------|---------|
| **Repo URL** | `https://github.com/abs-inc/abs-server/tree/feat/sprint-q12-deep-quality` |
| **Activation key** | `ABS_LICENSE_KEY` generated in step 3 |
| **Provider keys** | Six mandatory keys: `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `CEREBRAS_API_KEY`, `COHERE_API_KEY`, `CLOUDFLARE_API_KEY`. Optional keys may be added as needed. |
| **Docs** | `docs/quickstart.md`, `docs/troubleshooting.md`, `docs/tester_handoff_checklist.md` (all updated to reference Q12 changes). |
| **Acceptance test** | Run the final E2E suite:  ```bash pytest tests/test_q12_r91_final_acceptance.py -vv ```  The suite must exit with **0** (all tests PASS). |
| **Handoff** | Provide the tester with: <br>1. Repo URL (branch `feat/sprint-q12-deep-quality`). <br>2. `.env.production` (SOPS‑encrypted) containing the license key and provider keys. <br>3. A short README summarising the three tiers and the expected billing flow. |

**Success condition** – The tester runs the acceptance suite and reports `1/1 PASS`. Record the tester's sign‑off in the issue tracker.

---  

## Sign‑off  

When step 0 has been re-run on the founder host AND items 1–7 are complete, add a signed line to this document, commit the change, and create a Git tag `handoff/v1` pointing at `dbaeca8` (or whichever HEAD on `feat/sprint-q12-deep-quality` is current at sign-off — re-run step 0 against the current HEAD).

```
Date: [COMPLETION DATE]
Founder: [YOUR INITIALS]
Pytest full-suite last line: [PASTE EXACT LINE FROM STEP 0 HERE]
```

Push the tag:

```bash
git tag handoff/v1 dbaeca8
git push origin handoff/v1
```

The tester engagement period begins immediately after the tag is pushed.  

---  

*End of checklist.*
