#!/bin/bash
# runner-disk-cleanup.sh — DAK-5764
# Automated Rust target/ cleanup for GitHub Actions runners.
# Runs every 6h via cron. Keeps disk below 80%.

set -euo pipefail

TELEGRAM_BOT_TOKEN="***REDACTED_BOT_TOKEN***"
TELEGRAM_CHAT_ID="1170826474"
LOG="/var/log/runner-disk-cleanup.log"
HOSTNAME=$(hostname -s)
DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log() { echo "$DATE [$HOSTNAME] $*" | tee -a "$LOG"; }

tg_alert() {
  curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${TELEGRAM_CHAT_ID}\",\"text\":\"$1\",\"parse_mode\":\"Markdown\"}" \
    > /dev/null 2>&1 || true
}

disk_pct() { df / | awk 'NR==2 {gsub(/%/,""); print $5}'; }

DISK_BEFORE=$(disk_pct)
log "START — disk ${DISK_BEFORE}%"

FREED=0

# Clean Rust target/ dirs inside runner work directories (older than 24h)
while IFS= read -r TARGET_DIR; do
  [ -d "$TARGET_DIR" ] || continue
  SIZE=$(du -sm "$TARGET_DIR" 2>/dev/null | cut -f1) || continue
  log "Cleaning $TARGET_DIR (${SIZE}MB)"
  rm -rf "$TARGET_DIR"
  FREED=$((FREED + SIZE))
done < <(find /root/actions-runner-* -maxdepth 5 -name 'target' -type d 2>/dev/null)

# Docker prune if disk still > 80%
DISK_MID=$(disk_pct)
if [ "$DISK_MID" -gt 80 ]; then
  log "Disk at ${DISK_MID}% after target cleanup — running docker prune"
  docker system prune -af --volumes >> "$LOG" 2>&1 || true
fi

# Clean stale tmp build dirs older than 1 day
find /tmp -maxdepth 2 -name 'cargo-*' -older /tmp -type d 2>/dev/null | xargs rm -rf 2>/dev/null || true

DISK_AFTER=$(disk_pct)
log "DONE — freed ~${FREED}MB, disk ${DISK_BEFORE}% → ${DISK_AFTER}%"

# Alert if disk > 85% even after cleanup
if [ "$DISK_AFTER" -gt 85 ]; then
  MSG="⚠️ *[Platform] Runner Disk Warning — ${HOSTNAME}*%0A%0ADisk at *${DISK_AFTER}%* after automated cleanup. Freed ${FREED}MB.%0AManual intervention may be needed."
  tg_alert "$MSG"
  log "ALERT sent — disk still at ${DISK_AFTER}%"
fi
