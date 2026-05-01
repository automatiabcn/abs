#!/usr/bin/env bash
# Automatia ABS — Claude Code PreToolUse native hook (Mod A).
# Claude Code'dan gelen stdin JSON'ı ABS backend'e POST eder,
# response'u stdout'a basar (Claude Code hook JSON spec uyumlu).
#
# Kurulum: infra/install_native_hooks.sh tarafından ~/.claude/hooks/ altına
# kopyalanır ve settings.json hooks entry'sine bağlanır.

set -euo pipefail

ABS_URL="${ABS_HOOKS_URL:-http://localhost:8443/v1/hooks/dispatch}"
TIMEOUT="${ABS_HOOKS_TIMEOUT:-3}"
ERR_LOG="${ABS_HOOKS_ERR_LOG:-/tmp/abs_hook_errors.log}"

# stdin'i yakala
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT
cat > "$TMPFILE"

# log rotation (200KB veya 7 gün+)
if [ -f "$ERR_LOG" ]; then
  size=$(stat -f%z "$ERR_LOG" 2>/dev/null || stat -c%s "$ERR_LOG" 2>/dev/null || echo 0)
  if [ "$size" -gt 204800 ]; then
    tail -n 100 "$ERR_LOG" > "$ERR_LOG.tmp" 2>/dev/null && mv "$ERR_LOG.tmp" "$ERR_LOG"
  fi
fi

# Claude Code hook fail-safe: backend'e ulaşılamazsa sessiz "{}" döndür
if ! curl -s --max-time "$TIMEOUT" -X POST "$ABS_URL" \
      -H "Content-Type: application/json" \
      -d @"$TMPFILE" 2>>"$ERR_LOG"; then
  echo "{}"
fi
