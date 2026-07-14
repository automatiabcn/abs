#!/usr/bin/env bash
# 015 — ABS Central Watchdog deploy script (Hetzner CX11 / DO smallest VPS / similar).
#
# Kullanim (VPS root SSH):
#   curl -fsSL https://example.com/deploy.sh | bash
#   # veya
#   scp infra/watchdog/deploy.sh root@<vps>:/tmp/ && ssh root@<vps> 'bash /tmp/deploy.sh'
#
# Env override:
#   INSTALL_DIR=/opt/abs-watchdog WATCHDOG_USER=watchdog DISCORD_WEBHOOK=https://...
#
# For repo code: clone or scp into $INSTALL_DIR/src/watchdog/.

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/abs-watchdog}"
WATCHDOG_USER="${WATCHDOG_USER:-watchdog}"
DISCORD_WEBHOOK="${DISCORD_WEBHOOK:-}"

# 1. User + dirs
id -u "$WATCHDOG_USER" >/dev/null 2>&1 || useradd --system --create-home "$WATCHDOG_USER"
mkdir -p "$INSTALL_DIR"
chown -R "$WATCHDOG_USER:$WATCHDOG_USER" "$INSTALL_DIR"

# 2. Python venv + deps
sudo -u "$WATCHDOG_USER" python3 -m venv "$INSTALL_DIR/.venv"
sudo -u "$WATCHDOG_USER" "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$WATCHDOG_USER" "$INSTALL_DIR/.venv/bin/pip" install httpx pyyaml

# 3. Code (user must upload via git clone or scp)
echo ""
echo "NEXT (kod yukleme):"
echo "  git clone https://github.com/automatia/abs $INSTALL_DIR/src"
echo "  veya:"
echo "  scp infra/watchdog/* root@vps:$INSTALL_DIR/src/watchdog/"
echo ""

# 4. Cron (gunde 1 06:00 UTC)
cat > /etc/cron.d/abs-watchdog <<EOF
# ABS Watchdog — gunde 1 kez 06:00 UTC, provider scrape + Discord alert
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 6 * * *  $WATCHDOG_USER  cd $INSTALL_DIR/src && WATCHDOG_DISCORD_WEBHOOK='$DISCORD_WEBHOOK' .venv/bin/python -m watchdog.cron 2>&1 | logger -t abs-watchdog
EOF
chmod 644 /etc/cron.d/abs-watchdog

# 5. Logrotate (rsyslog → writes to /var/log/syslog; weekly rotate)
cat > /etc/logrotate.d/abs-watchdog <<'EOF'
/var/log/abs-watchdog.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
    create 0644 syslog adm
}
EOF

echo ""
echo "Deployed. Test komut:"
echo "  sudo -u $WATCHDOG_USER bash -c \"cd $INSTALL_DIR/src && WATCHDOG_DISCORD_WEBHOOK='$DISCORD_WEBHOOK' .venv/bin/python -m watchdog.cron\""
echo ""
echo "Cron loglari: journalctl -t abs-watchdog -f"
