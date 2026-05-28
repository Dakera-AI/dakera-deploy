#!/bin/bash
# runner-health-monitor.sh — DAK-5764
# Monitors all GitHub Actions runner services.
# Detects OOM kills and failed services, auto-restarts, alerts Telegram.
# Runs every 5min via systemd timer on both ARM and x64 runners.

set -euo pipefail

TELEGRAM_BOT_TOKEN="***REDACTED_BOT_TOKEN***"
TELEGRAM_CHAT_ID="1170826474"
STATE_DIR="/var/lib/runner-health"
HOSTNAME=$(hostname -s)
DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

mkdir -p "$STATE_DIR"

log() {
  echo "$DATE [$HOSTNAME] $*"
  logger -t runner-health-monitor "$*"
}

tg_alert() {
  local msg="$1"
  curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${TELEGRAM_CHAT_ID}\",\"text\":\"${msg}\",\"parse_mode\":\"Markdown\"}" \
    > /dev/null 2>&1 || true
}

RESTARTED=0
FAILED_UNITS=""
NOW=$(date +%s)

# --- Check all runner services ---
while IFS= read -r UNIT; do
  [ -z "$UNIT" ] && continue
  STATE=$(systemctl is-active "$UNIT" 2>/dev/null || echo "unknown")
  
  if [ "$STATE" != "active" ]; then
    log "ALERT: $UNIT is $STATE — restarting"
    systemctl restart "$UNIT" 2>/dev/null || true
    sleep 2
    NEW_STATE=$(systemctl is-active "$UNIT" 2>/dev/null || echo "unknown")
    log "Restart result: $UNIT is now $NEW_STATE"
    FAILED_UNITS="${FAILED_UNITS}\n• ${UNIT##actions.runner.dakera-ai-} (${STATE}→${NEW_STATE})"
    RESTARTED=$((RESTARTED + 1))
  fi
done < <(systemctl list-units 'actions.runner.*' --no-pager --no-legend --state=active,failed,dead,inactive 2>/dev/null | awk '{print $1}')

# --- OOM detection: check journal for OOM kills in last 6 minutes ---
OOM_PROCS=$(journalctl --since "6 minutes ago" --no-pager -q 2>/dev/null | \
  grep -i 'oom\|out of memory\|killed process' | \
  grep -i 'runner\|cargo\|rustc\|dakera' | head -5 || true)

if [ -n "$OOM_PROCS" ]; then
  log "OOM kill detected: $OOM_PROCS"
  # Find any dead runner units caused by OOM and restart
  while IFS= read -r UNIT; do
    [ -z "$UNIT" ] && continue
    systemctl restart "$UNIT" 2>/dev/null || true
    RESTARTED=$((RESTARTED + 1))
  done < <(systemctl list-units 'actions.runner.*' --no-pager --no-legend --state=failed,dead 2>/dev/null | awk '{print $1}')
  
  # 1-hour cooldown to prevent Telegram spam (DAK-5864)
  OOM_ALERT_FILE="$STATE_DIR/last-oom-alert"
  LAST_OOM_ALERT=$(cat "$OOM_ALERT_FILE" 2>/dev/null || echo 0)
  if [ $((NOW - LAST_OOM_ALERT)) -gt 3600 ]; then
    OOM_MSG="🔴 *[Platform] Runner OOM Detected — ${HOSTNAME}*%0A%0AOOM kill detected in journal. Affected runners restarted.%0A%0AContext:%0A\`$(echo "$OOM_PROCS" | head -2 | tr '\n' ' ' | cut -c1-200)\`"
    tg_alert "$OOM_MSG"
    echo "$NOW" > "$OOM_ALERT_FILE"
  else
    log "OOM detected — alert suppressed, cooldown $(( 3600 - (NOW - LAST_OOM_ALERT) ))s remaining"
  fi
fi

# --- Send Telegram alert for restarts ---
if [ "$RESTARTED" -gt 0 ]; then
  MSG="⚠️ *[Platform] Runner Auto-Restart — ${HOSTNAME}*%0A%0A${RESTARTED} runner(s) restarted:%0A$(echo -e "$FAILED_UNITS")%0A%0AAll runners checked and recovered."
  tg_alert "$MSG"
fi

# --- Periodic status log every 30min ---
TICK_FILE="$STATE_DIR/last-status-tick"
LAST_TICK=$(cat "$TICK_FILE" 2>/dev/null || echo 0)
if [ $((NOW - LAST_TICK)) -gt 1800 ]; then
  TOTAL=$(systemctl list-units 'actions.runner.*' --no-pager --no-legend 2>/dev/null | wc -l)
  ACTIVE=$(systemctl list-units 'actions.runner.*' --no-pager --no-legend --state=active 2>/dev/null | wc -l)
  DISK=$(df / | awk 'NR==2 {gsub(/%/,""); print $5}')
  MEM_FREE=$(free -m | awk '/^Mem:/{print $7}')
  log "STATUS: ${ACTIVE}/${TOTAL} runners active, disk ${DISK}%, mem ${MEM_FREE}MB free"
  echo "$NOW" > "$TICK_FILE"
fi
