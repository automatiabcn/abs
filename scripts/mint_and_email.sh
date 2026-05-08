#!/usr/bin/env bash
# mint_and_email.sh — founder one-command license + email.
#
# Wraps customer_onboard.sh and sends the bilingual license email via the
# Resend HTTP API. Designed so the founder can issue a license from
# anywhere (laptop, phone via SSH) without copy-pasting JWTs.
#
# USAGE
#   ./scripts/mint_and_email.sh customer@example.com self-host
#   ./scripts/mint_and_email.sh customer@example.com team-5
#   ./scripts/mint_and_email.sh customer@example.com team-10
#   ./scripts/mint_and_email.sh customer@example.com maintenance
#   ./scripts/mint_and_email.sh customer@example.com self-host --dry-run
#
# TIER MAPPING -> customer_onboard.sh (real_tier seats valid_days)
#   self-host    -> self-host 1  365
#   team-5       -> team      5  365
#   team-10      -> team      10 365
#   maintenance  -> self-host 1  30
#
# RESEND API KEY RESOLUTION (in order)
#   1. $RESEND_API_KEY env var
#   2. $HOME/.config/automatia/.resend-api-key
#   3. ssh ai-pc 'cat ~/keys/resend-api-key'

set -euo pipefail
cd "$(dirname "$0")/.."

# ---------- colour helpers ----------
if [ -t 1 ]; then
  C_HDR='\033[1;36m'; C_OK='\033[1;32m'; C_WARN='\033[1;33m'; C_ERR='\033[1;31m'; C_OFF='\033[0m'
else
  C_HDR=''; C_OK=''; C_WARN=''; C_ERR=''; C_OFF=''
fi
hdr() { printf "${C_HDR}%s${C_OFF}\n" "$*"; }
warn() { printf "${C_WARN}WARN:${C_OFF} %s\n" "$*" >&2; }
err()  { printf "${C_ERR}ERROR:${C_OFF} %s\n" "$*" >&2; }
ok()   { printf "${C_OK}%s${C_OFF}\n" "$*"; }

usage() {
  cat <<USAGE
Usage: $0 <email> <tier> [--dry-run]
  tier: self-host | team-5 | team-10 | maintenance
USAGE
  exit 2
}

# ---------- 1/7 parse args ----------
DRY_RUN=0
EMAIL=""
TIER=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) usage ;;
    *)
      if [ -z "$EMAIL" ]; then EMAIL="$arg"
      elif [ -z "$TIER" ]; then TIER="$arg"
      else err "unexpected positional arg: $arg"; usage; fi
      ;;
  esac
done

[ -n "$EMAIL" ] || { err "email required"; usage; }
[ -n "$TIER" ]  || { err "tier required"; usage; }

if ! [[ "$EMAIL" =~ ^[^@]+@[^@]+\.[^@]+$ ]]; then
  err "invalid email format: $EMAIL"; exit 1
fi

case "$TIER" in
  self-host)   REAL_TIER="self-host"; SEATS=1;  VALID_DAYS=365 ;;
  team-5)      REAL_TIER="team";      SEATS=5;  VALID_DAYS=365 ;;
  team-10)     REAL_TIER="team";      SEATS=10; VALID_DAYS=365 ;;
  maintenance) REAL_TIER="self-host"; SEATS=1;  VALID_DAYS=30  ;;
  *) err "invalid tier: $TIER (expected self-host|team-5|team-10|maintenance)"; exit 1 ;;
esac

# ---------- 2/7 derive customer name ----------
LOCAL_PART="${EMAIL%@*}"
SAFE_LOCAL=$(printf '%s' "$LOCAL_PART" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')
[ -n "$SAFE_LOCAL" ] || { err "email local-part has no [a-z0-9] characters"; exit 1; }
TS="$(date +%s)"
CUSTOMER_NAME="${SAFE_LOCAL}-${TS}"
SLUG=$(printf '%s' "$CUSTOMER_NAME" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9-')

hdr "[1/7] Customer: $CUSTOMER_NAME (slug=$SLUG, tier=$TIER -> $REAL_TIER seats=$SEATS valid=$VALID_DAYS)"

# ---------- 3/7 mint license via customer_onboard.sh ----------
hdr "[2/7] Minting license via customer_onboard.sh"
if ! ./scripts/customer_onboard.sh \
      "$CUSTOMER_NAME" "$EMAIL" "$REAL_TIER" "$SEATS" "$VALID_DAYS"; then
  err "customer_onboard.sh failed"; exit 1
fi

JWT_FILE="customer-keys/${SLUG}/license.jwt"
if [ ! -s "$JWT_FILE" ]; then
  err "license file missing or empty: $JWT_FILE"; exit 1
fi
JWT="$(tr -d '\r\n' < "$JWT_FILE")"

# ---------- 4/7 extract jti ----------
hdr "[3/7] Extracting JTI"
JTI="$(JWT="$JWT" python3 - <<'PY'
import os, base64, json, sys
tok = os.environ["JWT"]
parts = tok.split(".")
if len(parts) < 2:
    sys.stderr.write("malformed JWT\n"); sys.exit(1)
payload = parts[1]
payload += "=" * (-len(payload) % 4)
data = json.loads(base64.urlsafe_b64decode(payload))
print(data["jti"])
PY
)"
[ -n "$JTI" ] || { err "failed to extract jti"; exit 1; }

# ---------- 5/7 read GHCR PAT (placeholder-aware) ----------
GHCR_FILE="customer-keys/${SLUG}/ghcr_pull.token"
GHCR_PAT="(see separate secure channel)"
if [ -s "$GHCR_FILE" ]; then
  GHCR_RAW="$(tr -d '\r\n' < "$GHCR_FILE")"
  if [ "$GHCR_RAW" = "__REPLACE_WITH_PAT_FROM_GITHUB__" ]; then
    warn "ghcr_pull.token still has placeholder — sending fallback notice in email"
  elif [ -n "$GHCR_RAW" ]; then
    GHCR_PAT="$GHCR_RAW"
  fi
fi

# ---------- 6/7 build email payload ----------
hdr "[4/7] Composing bilingual email payload"
SUBJECT="Your ABS license is ready / ABS lisansınız hazır"
TIER_DISPLAY="$TIER (real=$REAL_TIER seats=$SEATS valid_days=$VALID_DAYS)"
SETUP_URL="https://automatiabcn.com/products/abs/setup-guide"
SUPPORT_EMAIL="founder@automatiabcn.com"

# HTML body — use a heredoc with no command substitution besides scalar vars.
EMAIL_HTML=$(cat <<HTML
<!DOCTYPE html>
<html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#222;max-width:640px;">
<h2>Your ABS license is ready 🚀 / ABS lisansınız hazır 🚀</h2>

<p><strong>EN —</strong> Thanks for choosing Automatia ABS. Below are the two
secrets you need to launch your stack.</p>
<p><strong>TR —</strong> Automatia ABS&#39;i tercih ettiğiniz için teşekkürler. Aşağıda
yığını başlatmak için ihtiyacınız olan iki gizli değer bulunmaktadır.</p>

<h3>1. License JWT / Lisans JWT</h3>
<p><em>EN — Paste this into your <code>.env</code> as <code>ABS_LICENSE_KEY</code>.<br>
TR — Bu değeri <code>.env</code> dosyanıza <code>ABS_LICENSE_KEY</code> olarak yapıştırın.</em></p>
<pre style="background:#f4f4f4;padding:10px;font-size:12px;word-break:break-all;font-family:monospace;">${JWT}</pre>

<h3>2. GHCR pull token / GHCR çekme tokenı</h3>
<p><em>EN — Use this when running:<br>
<code>echo &quot;TOKEN&quot; | docker login ghcr.io -u &lt;your-github-user&gt; --password-stdin</code><br>
TR — <code>docker login ghcr.io</code> komutunu çalıştırırken bu tokenı kullanın.</em></p>
<pre style="background:#f4f4f4;padding:10px;font-size:12px;word-break:break-all;font-family:monospace;">${GHCR_PAT}</pre>

<h3>Setup guide / Kurulum kılavuzu</h3>
<p><a href="${SETUP_URL}">${SETUP_URL}</a></p>

<hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
<p><strong>Tier:</strong> ${TIER_DISPLAY}</p>
<p>EN — Need help? Reply to this email or write to
<a href="mailto:${SUPPORT_EMAIL}">${SUPPORT_EMAIL}</a>.<br>
TR — Yardıma mı ihtiyacınız var? Bu e-postayı yanıtlayın ya da
<a href="mailto:${SUPPORT_EMAIL}">${SUPPORT_EMAIL}</a> adresine yazın.</p>
<p style="color:#888;font-size:12px;">— Automatia BCN</p>
</body></html>
HTML
)

EMAIL_TEXT=$(cat <<TXT
Your ABS license is ready / ABS lisansınız hazır

License JWT (paste into .env as ABS_LICENSE_KEY):
${JWT}

GHCR pull token (use with: docker login ghcr.io -u <your-github-user>):
${GHCR_PAT}

Setup guide / Kurulum kılavuzu:
${SETUP_URL}

Tier: ${TIER_DISPLAY}

Need help? Reply to this email or write to ${SUPPORT_EMAIL}.

— Automatia BCN
TXT
)

# Build JSON payload via python3 (passes scalars through env to avoid shell escaping pitfalls)
PAYLOAD="$(
  EMAIL="$EMAIL" \
  SUBJECT="$SUBJECT" \
  HTML_BODY="$EMAIL_HTML" \
  TEXT_BODY="$EMAIL_TEXT" \
  python3 - <<'PY'
import json, os
payload = {
    "from": "Automatia BCN <hello@automatiabcn.com>",
    "to": [os.environ["EMAIL"]],
    "subject": os.environ["SUBJECT"],
    "html": os.environ["HTML_BODY"],
    "text": os.environ["TEXT_BODY"],
    "reply_to": ["founder@automatiabcn.com"],
}
print(json.dumps(payload, ensure_ascii=False))
PY
)"

# ---------- 7/7 resolve key + send ----------
hdr "[5/7] Resolving Resend API key"
RESEND_KEY=""
if [ -n "${RESEND_API_KEY:-}" ]; then
  RESEND_KEY="$RESEND_API_KEY"
elif [ -r "$HOME/.config/automatia/.resend-api-key" ]; then
  RESEND_KEY="$(tr -d '\r\n' < "$HOME/.config/automatia/.resend-api-key")"
elif RESEND_KEY="$(ssh -o ConnectTimeout=3 -o BatchMode=yes ai-pc \
                     'cat ~/keys/resend-api-key' 2>/dev/null)"; then
  RESEND_KEY="$(printf '%s' "$RESEND_KEY" | tr -d '\r\n')"
fi
if [ -z "$RESEND_KEY" ] && [ "$DRY_RUN" -eq 0 ]; then
  err "Resend API key not found (env / ~/.config/automatia/ / ai-pc:~/keys)"; exit 1
fi

ISO_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
LOG_DIR="customer-keys/_log"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/mint_email.log"

RESEND_ID="NA"
STATUS="failed"

if [ "$DRY_RUN" -eq 1 ]; then
  hdr "[6/7] DRY RUN — would POST to https://api.resend.com/emails:"
  printf '%s\n' "$PAYLOAD" \
    | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin),indent=2,ensure_ascii=False))'
  STATUS="dry_run"
else
  hdr "[6/7] Sending email via Resend API"
  HTTP_BODY=""
  if HTTP_BODY="$(curl -fsS -X POST https://api.resend.com/emails \
        -H "Authorization: Bearer $RESEND_KEY" \
        -H "Content-Type: application/json" \
        --data-binary @- <<<"$PAYLOAD")"; then
    if command -v jq >/dev/null 2>&1; then
      RESEND_ID="$(printf '%s' "$HTTP_BODY" | jq -r '.id // "NA"')"
    else
      RESEND_ID="$(printf '%s' "$HTTP_BODY" \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id","NA"))')"
    fi
    if [ -n "$RESEND_ID" ] && [ "$RESEND_ID" != "NA" ] && [ "$RESEND_ID" != "null" ]; then
      STATUS="sent"
      ok "Email sent (resend_id=$RESEND_ID)"
    else
      err "Resend response missing id: $HTTP_BODY"
    fi
  else
    err "curl to Resend failed: ${HTTP_BODY:-no body}"
  fi
fi

# Log line
printf '%s | %s | %s | %s | %s | resend_id=%s | slug=%s\n' \
  "$ISO_TS" "$EMAIL" "$JTI" "$TIER" "$STATUS" "$RESEND_ID" "$SLUG" >> "$LOG_FILE"

[ "$STATUS" = "failed" ] && exit 1

# ---------- final banner ----------
hdr "[7/7] Done"
cat <<BANNER
=== Done ===
Customer:    $CUSTOMER_NAME
Slug:        $SLUG
Email:       $EMAIL
Tier:        $TIER (mapped -> $REAL_TIER seats=$SEATS valid_days=$VALID_DAYS)
JTI:         $JTI
Resend ID:   $([ "$DRY_RUN" -eq 1 ] && echo "(dry-run, not sent)" || echo "$RESEND_ID")
Files:       customer-keys/$SLUG/
Log:         $LOG_FILE
BANNER
