#!/bin/bash
# playground-monitor.sh — DAK-6745
# Monitors Dakera Playground health: HTTP endpoint, Docker containers, disk, memory.
# Runs every 5min via systemd timer on playground server (5.75.177.31).
# Alerts Telegram on failure with 5-min cooldown per check type.

set -euo pipefail

TELEGRAM_BOT_TOKEN="***REDACTED_BOT_TOKEN***"
TELEGRAM_CHAT_ID="1170826474"
STATE_DIR="/var/lib/playground-health"
PLAYGROUND_URL="https://5-75-177-31.sslip.io/health"
DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Thresholds
DISK_ALERT_PCT=80
MEM_ALERT_PCT=90
# Cooldowns (seconds) — prevent Telegram spam
HEALTH_COOLDOWN=300     # 5min — alert every failure run for health (endpoint is critical)
DISK_COOLDOWN=3600      # 1h — disk doesn't change that fast
MEM_COOLDOWN=1800       # 30min
CONTAINER_COOLDOWN=300  # 5min — containers must stay up

CONTAINERS=("playground-dakera" "playground-sandbox-proxy" "playground-minio")

mkdir -p "$STATE_DIR"

log() {
  echo "$DATE [playground-monitor] $*"
  logger -t playground-monitor "$*" 2>/dev/null || true
}

tg_alert() {
  local msg="$1"
  curl -sf --max-time 10 -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${TELEGRAM_CHAT_ID}\",\"text\":\"${msg}\",\"parse_mode\":\"Markdown\"}" \
    > /dev/null 2>&1 || true
}

# Returns 1 if cooldown has NOT expired yet (should suppress)
in_cooldown() {
  local key="$1" cooldown="$2"
  local file="$STATE_DIR/last-alert-${key}"
  local now last
  now=$(date +%s)
  last=$(cat "$file" 2>/dev/null || echo 0)
  if [ $((now - last)) -lt "$cooldown" ]; then
    return 0
  fi
  return 1
}

reset_cooldown() {
  local key="$1"
  echo "$(date +%s)" > "$STATE_DIR/last-alert-${key}"
}

clear_cooldown() {
  local key="$1"
  rm -f "$STATE_DIR/last-alert-${key}"
}

ALERTS=""

# --- 1. HTTP Health Check ---
HTTP_STATUS=$(curl -sf --max-time 10 -o /dev/null -w "%{http_code}" "$PLAYGROUND_URL" 2>/dev/null || echo "000")
if [ "$HTTP_STATUS" = "200" ]; then
  log "Health check OK (HTTP $HTTP_STATUS)"
  clear_cooldown "health"
else
  log "ALERT: Health check FAILED (HTTP $HTTP_STATUS, URL=$PLAYGROUND_URL)"
  if ! in_cooldown "health" "$HEALTH_COOLDOWN"; then
    ALERTS="${ALERTS}🔴 *[Playground] Health Check FAILED*\nURL: \`${PLAYGROUND_URL}\`\nStatus: HTTP ${HTTP_STATUS}\nTime: ${DATE}\n\n"
    reset_cooldown "health"
  fi
fi

# --- 2. Container Health Check ---
MISSING_CONTAINERS=""
for CONTAINER in "${CONTAINERS[@]}"; do
  STATUS=$(docker inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "missing")
  if [ "$STATUS" != "running" ]; then
    log "ALERT: Container $CONTAINER is $STATUS"
    MISSING_CONTAINERS="${MISSING_CONTAINERS}\n• ${CONTAINER}: *${STATUS}*"
  else
    log "Container $CONTAINER: running"
  fi
done

if [ -n "$MISSING_CONTAINERS" ]; then
  clear_cooldown "containers"
  if ! in_cooldown "containers" "$CONTAINER_COOLDOWN"; then
    ALERTS="${ALERTS}🔴 *[Playground] Container(s) Down*\nTime: ${DATE}${MISSING_CONTAINERS}\n\n"
    reset_cooldown "containers"
  fi
else
  clear_cooldown "containers"
fi

# --- 3. Disk Usage Check ---
DISK_PCT=$(df / | awk 'NR==2 {gsub(/%/,""); print $5}')
DISK_FREE=$(df -h / | awk 'NR==2 {print $4}')
log "Disk: ${DISK_PCT}% used, ${DISK_FREE} free"

if [ "$DISK_PCT" -ge "$DISK_ALERT_PCT" ]; then
  log "ALERT: Disk usage ${DISK_PCT}% >= threshold ${DISK_ALERT_PCT}%"
  if ! in_cooldown "disk" "$DISK_COOLDOWN"; then
    ALERTS="${ALERTS}⚠️ *[Playground] Disk Usage High*\nUsed: ${DISK_PCT}% (threshold: ${DISK_ALERT_PCT}%)\nFree: ${DISK_FREE}\nTime: ${DATE}\n\n"
    reset_cooldown "disk"
  fi
else
  clear_cooldown "disk"
fi

# --- 4. Memory Usage Check ---
MEM_TOTAL=$(free -m | awk '/^Mem:/{print $2}')
MEM_USED=$(free -m | awk '/^Mem:/{print $3}')
MEM_PCT=0
if [ "$MEM_TOTAL" -gt 0 ]; then
  MEM_PCT=$(( (MEM_USED * 100) / MEM_TOTAL ))
fi
MEM_FREE_MB=$(free -m | awk '/^Mem:/{print $7}')
log "Memory: ${MEM_PCT}% used (${MEM_USED}/${MEM_TOTAL}MB, ${MEM_FREE_MB}MB available)"

if [ "$MEM_PCT" -ge "$MEM_ALERT_PCT" ]; then
  log "ALERT: Memory usage ${MEM_PCT}% >= threshold ${MEM_ALERT_PCT}%"
  if ! in_cooldown "memory" "$MEM_COOLDOWN"; then
    ALERTS="${ALERTS}⚠️ *[Playground] Memory Usage High*\nUsed: ${MEM_PCT}% (${MEM_USED}/${MEM_TOTAL}MB)\nAvailable: ${MEM_FREE_MB}MB\nTime: ${DATE}\n\n"
    reset_cooldown "memory"
  fi
else
  clear_cooldown "memory"
fi

# --- 5. Send combined Telegram alert ---
if [ -n "$ALERTS" ]; then
  tg_alert "$ALERTS"
  log "Telegram alert sent"
fi

# --- 6. Periodic status log (every 30min) ---
TICK_FILE="$STATE_DIR/last-status-tick"
NOW=$(date +%s)
LAST_TICK=$(cat "$TICK_FILE" 2>/dev/null || echo 0)
if [ $((NOW - LAST_TICK)) -gt 1800 ]; then
  RUNNING=$(docker ps --filter "name=$(printf '%s|' "${CONTAINERS[@]}" | sed 's/|$//')" --format '{{.Names}}' 2>/dev/null | wc -l || echo 0)
  log "STATUS: HTTP=${HTTP_STATUS} containers=${RUNNING}/${#CONTAINERS[@]} disk=${DISK_PCT}% mem=${MEM_PCT}%"
  echo "$NOW" > "$TICK_FILE"
fi
