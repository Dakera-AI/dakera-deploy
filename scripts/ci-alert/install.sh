#!/bin/bash
# Install the CI Failure Alerting Webhook on the production server.
# DAK-4572 — GitHub webhook → Paperclip issue creation.
#
# Run as root on 178.104.45.161:
#   bash install.sh
#
# Prerequisites:
#   - python3 (system)
#   - node / npx + paperclipai (for Paperclip API calls)
#   - /etc/ci-alert/env populated with real values (see ci-alert-webhook.env.example)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/ci-alert"
ENV_DIR="/etc/ci-alert"
SERVICE_NAME="ci-alert-webhook"
PORT="${CI_ALERT_PORT:-8765}"

echo "==> Installing CI alert webhook to ${INSTALL_DIR}"

# 1. Create directories
mkdir -p "${INSTALL_DIR}" "${ENV_DIR}" /var/log/ci-alert

# 2. Copy webhook script
cp "${SCRIPT_DIR}/ci-alert-webhook.py" "${INSTALL_DIR}/ci-alert-webhook.py"
chmod +x "${INSTALL_DIR}/ci-alert-webhook.py"

# 3. Create env file if it doesn't exist (populate manually or via secrets manager)
if [ ! -f "${ENV_DIR}/env" ]; then
    echo "==> Creating ${ENV_DIR}/env from example — fill in real values before starting"
    cp "${SCRIPT_DIR}/ci-alert-webhook.env.example" "${ENV_DIR}/env"
    chmod 600 "${ENV_DIR}/env"
fi

# 4. Install systemd unit
cp "${SCRIPT_DIR}/ci-alert-webhook.service" "/etc/systemd/system/${SERVICE_NAME}.service"

# 5. Open firewall port (UFW)
if command -v ufw >/dev/null 2>&1; then
    echo "==> Allowing port ${PORT}/tcp in UFW"
    ufw allow "${PORT}/tcp" comment "ci-alert-webhook GitHub" || true
else
    echo "==> UFW not found — ensure port ${PORT} is open in your firewall"
fi

# 6. Enable and start service
echo "==> Enabling and starting ${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

# 7. Verify
sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "==> Service is running"
    HEALTH=$(curl -sf "http://127.0.0.1:${PORT}/health" 2>/dev/null || echo "no-response")
    echo "==> Health check: ${HEALTH}"
else
    echo "ERROR: Service failed to start — check logs:"
    journalctl -u "${SERVICE_NAME}" -n 30 --no-pager
    exit 1
fi

echo ""
echo "==> CI alert webhook installed successfully."
echo "    Webhook URL (register this in GitHub org settings):"
echo "    http://$(hostname -I | awk '{print $1}'):${PORT}/webhook"
echo ""
echo "    Verify env file: ${ENV_DIR}/env"
echo "    Logs: journalctl -fu ${SERVICE_NAME}"
