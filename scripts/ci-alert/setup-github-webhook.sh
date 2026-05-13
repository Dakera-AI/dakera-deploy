#!/bin/bash
# Register the CI failure alerting webhook on the dakera-ai GitHub org.
# DAK-4572 — one-time setup. Run from a machine with 'gh' authenticated as org admin.
#
# Usage:
#   WEBHOOK_URL=http://178.104.45.161:8765/webhook \
#   WEBHOOK_SECRET=<your-secret> \
#   bash setup-github-webhook.sh
#
# The secret must match GITHUB_WEBHOOK_SECRET in /etc/ci-alert/env on the prod server.

set -euo pipefail

ORG="dakera-ai"
WEBHOOK_URL="${WEBHOOK_URL:?Set WEBHOOK_URL=http://<prod-ip>:8765/webhook}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:?Set WEBHOOK_SECRET to the HMAC secret}"

echo "==> Registering org-level webhook for ${ORG}"
echo "    URL: ${WEBHOOK_URL}"

# Check for existing webhook with same URL to avoid duplicates
EXISTING=$(gh api "orgs/${ORG}/hooks" | jq -r ".[] | select(.config.url == \"${WEBHOOK_URL}\") | .id")
if [ -n "${EXISTING}" ]; then
    echo "==> Webhook already exists (ID: ${EXISTING}) — updating config"
    gh api -X PATCH "orgs/${ORG}/hooks/${EXISTING}" \
        -f "config[url]=${WEBHOOK_URL}" \
        -f "config[content_type]=json" \
        -f "config[secret]=${WEBHOOK_SECRET}" \
        -f "config[insecure_ssl]=0" \
        -F "events[]=workflow_run" \
        -F "active=true" | jq '{id: .id, url: .config.url, events: .events, active: .active}'
else
    echo "==> Creating new org webhook"
    gh api -X POST "orgs/${ORG}/hooks" \
        -f "name=web" \
        -f "config[url]=${WEBHOOK_URL}" \
        -f "config[content_type]=json" \
        -f "config[secret]=${WEBHOOK_SECRET}" \
        -f "config[insecure_ssl]=0" \
        -F "events[]=workflow_run" \
        -F "active=true" | jq '{id: .id, url: .config.url, events: .events, active: .active}'
fi

echo ""
echo "==> Done. The webhook will now deliver workflow_run events to:"
echo "    ${WEBHOOK_URL}"
echo ""
echo "    Verify with: gh api orgs/${ORG}/hooks | jq '.[].config.url'"
echo "    Test delivery: gh api -X POST orgs/${ORG}/hooks/<id>/pings"
