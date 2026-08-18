#!/usr/bin/env bash
# Deploy the licence authority Worker and PROVE the routes exist afterwards.
#
# Why this file exists (2026-08-18): the Worker source has had /v1/renew since
# 2026-07-15 and its tests pass, but the DEPLOYED Worker was the 2026-05-10
# build — live /v1/renew answered {"error":"not_found"}. A paying customer's
# second month would have fallen into the 7-day grace and then locked. Code in
# a repository is not a deployment; this script does the deployment and then
# asks the live host, so "deployed" means the route answers.
#
# Needs a Cloudflare login with Workers Scripts:Edit on the account:
#   wrangler login            (browser; the OAuth token expires — it did)
# and, if never set on this Worker, the secrets named in wrangler.toml.
#
#   infra/cf-worker/deploy.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${ABS_LICENSE_WORKER_HOST:-https://abs-license-activation.automatiaabs.workers.dev}"

cd "$HERE"
echo "== tests (no network)"
node --test licensing.test.mjs >/dev/null || { echo "worker tests red — not deploying"; exit 1; }

echo "== who am I"
if ! wrangler whoami >/dev/null 2>&1; then
  echo "wrangler is not logged in (or the token lacks Workers permissions)."
  echo "Run:  wrangler login   — then re-run this script."
  exit 1
fi

echo "== deploy"
wrangler deploy

echo "== prove the routes answer"
for path in /health /v1/renew /v1/activate /v1/heartbeat; do
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$HOST$path" -H 'Content-Type: application/json' -d '{}')"
  case "$path:$code" in
    /health:200|/health:405) echo "   ok  $path ($code)";;
    /v1/*:400|/v1/*:401|/v1/*:402|/v1/*:422) echo "   ok  $path answers ($code — refused an empty body, as it should)";;
    *:404) echo "   FAIL $path is not deployed ($code)"; exit 1;;
    *) echo "   ??  $path -> $code (look at it)";;
  esac
done
echo "deployed and answering: $HOST"
