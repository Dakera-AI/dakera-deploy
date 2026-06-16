#!/usr/bin/env bash
# install-monitor.sh — installs playground-monitor on playground server via SSH
# Usage: SSH_KEY=~/.ssh/id_ed25519 PLAYGROUND_IP=<server-ip> ./install-monitor.sh
# DAK-6745

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAYGROUND_IP="${PLAYGROUND_IP:?PLAYGROUND_IP must be set}"
SSH_KEY="${SSH_KEY:-${HOME}/.ssh/id_ed25519}"
SSH="ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=15 root@${PLAYGROUND_IP}"

echo "[install-monitor] Deploying to ${PLAYGROUND_IP}..."

# Upload script
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no \
  "${SCRIPT_DIR}/playground-monitor.sh" \
  "root@${PLAYGROUND_IP}:/usr/local/bin/playground-monitor.sh"

$SSH chmod +x /usr/local/bin/playground-monitor.sh

# Upload systemd units
scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no \
  "${SCRIPT_DIR}/playground-monitor.service" \
  "root@${PLAYGROUND_IP}:/etc/systemd/system/playground-monitor.service"

scp -i "${SSH_KEY}" -o StrictHostKeyChecking=no \
  "${SCRIPT_DIR}/playground-monitor.timer" \
  "root@${PLAYGROUND_IP}:/etc/systemd/system/playground-monitor.timer"

# Enable and start
$SSH bash -s << 'REMOTE'
set -euo pipefail
mkdir -p /var/lib/playground-health
systemctl daemon-reload
systemctl enable playground-monitor.timer
systemctl start playground-monitor.timer
systemctl status playground-monitor.timer --no-pager
echo "[install-monitor] Timer active — running health check once to verify..."
systemctl start playground-monitor.service
journalctl -u playground-monitor.service -n 20 --no-pager 2>/dev/null || true
echo "[install-monitor] Done."
REMOTE

echo "[install-monitor] Monitor installed and running on ${PLAYGROUND_IP}."
