#!/bin/bash
# Install automated Docker cleanup systemd timer on self-hosted runner host
# Run as root on the Hetzner ARM server.
# Usage: bash install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing docker-cleanup.sh..."
cp "$SCRIPT_DIR/docker-cleanup.sh" /usr/local/bin/docker-cleanup.sh
chmod +x /usr/local/bin/docker-cleanup.sh

echo "Installing systemd units..."
cp "$SCRIPT_DIR/docker-cleanup.service" /etc/systemd/system/docker-cleanup.service
cp "$SCRIPT_DIR/docker-cleanup.timer" /etc/systemd/system/docker-cleanup.timer

echo "Enabling and starting timer..."
systemctl daemon-reload
systemctl enable docker-cleanup.timer
systemctl start docker-cleanup.timer

echo "Done. Timer status:"
systemctl status docker-cleanup.timer --no-pager
echo ""
echo "Next trigger: $(systemctl show docker-cleanup.timer --property=NextElapseUSecRealtime | cut -d= -f2)"
