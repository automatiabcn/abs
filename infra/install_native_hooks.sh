#!/usr/bin/env bash
# Automatia ABS — Claude Code native hook kurulum scripti (Mod A opsiyonel).
#
# Kullanıcının ~/.claude/hooks/ altına ABS pre-tool-guard.sh'i symlink'ler ve
# settings.json PreToolUse hook entry'sini ekler (zaten varsa override etmez).
#
# Çalıştırma: bash infra/install_native_hooks.sh

set -euo pipefail

PRODUCT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$PRODUCT_ROOT/core/native-hooks/pre-tool-guard.sh"
DEST_DIR="$HOME/.claude/hooks"
DEST="$DEST_DIR/abs-pre-tool-guard.sh"

if [ ! -f "$SRC" ]; then
  echo "HATA: $SRC bulunamadı. ABS kurulumunu kontrol edin."
  exit 1
fi

mkdir -p "$DEST_DIR"
chmod +x "$SRC"

if [ -e "$DEST" ] && [ ! -L "$DEST" ]; then
  echo "UYARI: $DEST zaten var ve symlink değil — override etmedim."
  echo "Manuel kurulum için: ln -sf \"$SRC\" \"$DEST\""
  exit 1
fi

ln -sf "$SRC" "$DEST"
echo "[OK] $DEST → $SRC"

echo ""
echo "Claude Code settings.json'a aşağıdaki hook entry'sini ekleyin:"
echo ""
cat <<EOF
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          { "type": "command", "command": "$DEST" }
        ]
      }
    ]
  }
EOF
echo ""
echo "ABS backend URL: \$ABS_HOOKS_URL (default: http://localhost:8443/v1/hooks/dispatch)"
