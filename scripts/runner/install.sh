#!/bin/bash
# install.sh — Deploy runner health monitor and disk cleanup automation
# DAK-5764: Platform reliability — deploy pipeline hardening + runner health automation
#
# Run on each GitHub Actions runner host (ARM: 168.119.60.30, x64: 178.104.227.173)
# Requires: root, systemd, TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" != "0" ]; then
  echo "Must run as root" >&2
  exit 1
fi

echo "[runner/install.sh] Installing runner automation to $(hostname)..."

# Health monitor (systemd timer — every 5min)
cp "$SCRIPT_DIR/runner-health-monitor.sh" /usr/local/bin/runner-health-monitor.sh
chmod +x /usr/local/bin/runner-health-monitor.sh
cp "$SCRIPT_DIR/runner-health-monitor.service" /etc/systemd/system/runner-health-monitor.service
cp "$SCRIPT_DIR/runner-health-monitor.timer" /etc/systemd/system/runner-health-monitor.timer

# Disk cleanup (ARM: cron every 6h, x64: cron every 4h)
cp "$SCRIPT_DIR/runner-disk-cleanup.sh" /usr/local/bin/runner-disk-cleanup.sh
chmod +x /usr/local/bin/runner-disk-cleanup.sh

systemctl daemon-reload
systemctl enable --now runner-health-monitor.timer

echo "[runner/install.sh] Done. Timer status:"
systemctl list-timers runner-health-monitor.timer --no-pager
