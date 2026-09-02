#!/usr/bin/env sh
# =============================================================================
# dakera-watchdog.sh  (DAK-9890)
# -----------------------------------------------------------------------------
# Polls the dakera container health and memory every DAKERA_WATCHDOG_POLL_SECS
# seconds. Two actions:
#   1. Health streak > DAKERA_WATCHDOG_RESTART_AFTER → restart + Telegram alert
#   2. Memory > DAKERA_WATCHDOG_MEM_ALERT_PCT of limit → Telegram warning
#
# Runs inside the dakera-watchdog compose sidecar (docker:cli image) with the
# host Docker socket mounted. Only ever touches the 'dakera' container.
#
# Environment (all optional — no Telegram = log-only):
#   TELEGRAM_BOT_TOKEN        Telegram bot token for alerts
#   TELEGRAM_CHAT_ID          Telegram chat ID to send alerts to
#   DAKERA_WATCHDOG_RESTART_AFTER   Failing streak threshold before restart (default 5)
#   DAKERA_WATCHDOG_MEM_ALERT_PCT   Memory % threshold for warning (default 90)
#   DAKERA_WATCHDOG_POLL_SECS       Poll interval in seconds (default 30)
# =============================================================================
set -eu

CONTAINER="${DAKERA_CONTAINER_NAME:-dakera}"
RESTART_AFTER="${DAKERA_WATCHDOG_RESTART_AFTER:-5}"
MEM_ALERT_PCT="${DAKERA_WATCHDOG_MEM_ALERT_PCT:-90}"
POLL_SECS="${DAKERA_WATCHDOG_POLL_SECS:-30}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

# Track consecutive memory-alert count to avoid alert spam (re-alert every 10 cycles)
MEM_ALERT_COUNT=0
LAST_MEM_ALERT_CYCLE=0
CYCLE=0

tg_send() {
  msg="$1"
  if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "[watchdog] ALERT (no Telegram): $msg"
    return
  fi
  # shellcheck disable=SC2018,SC2019
  encoded=$(printf '%s' "$msg" | \
    sed 's/&/%26/g; s/=/%3D/g; s/?/%3F/g; s/ /%20/g; s/\n/%0A/g; s/</%3C/g; s/>/%3E/g')
  wget -qO- \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --post-data="chat_id=${TELEGRAM_CHAT_ID}&text=${encoded}&parse_mode=HTML" \
    2>&1 | grep -q '"ok":true' \
    && echo "[watchdog] Telegram sent." \
    || echo "[watchdog] Telegram send failed — logged only."
}

check_container_exists() {
  docker inspect "$CONTAINER" >/dev/null 2>&1
}

get_failing_streak() {
  docker inspect "$CONTAINER" \
    --format '{{if .State.Health}}{{.State.Health.FailingStreak}}{{else}}-1{{end}}' \
    2>/dev/null || echo "-1"
}

get_health_status() {
  docker inspect "$CONTAINER" \
    --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
    2>/dev/null || echo "unknown"
}

# docker stats --format '{{.MemPerc}}' returns e.g. "88.50%"
get_mem_pct() {
  docker stats "$CONTAINER" --no-stream --format '{{.MemPerc}}' 2>/dev/null \
    | sed 's/%//' | cut -d. -f1
}

echo "[watchdog] Starting. container=${CONTAINER} restart_after=${RESTART_AFTER} mem_alert_pct=${MEM_ALERT_PCT}% poll=${POLL_SECS}s"

while true; do
  CYCLE=$((CYCLE + 1))
  sleep "$POLL_SECS"

  if ! check_container_exists; then
    echo "[watchdog] Container '${CONTAINER}' not found — skipping cycle ${CYCLE}."
    continue
  fi

  # ── Health streak check ──────────────────────────────────────────────────
  STREAK=$(get_failing_streak)
  STATUS=$(get_health_status)

  echo "[watchdog] cycle=${CYCLE} health=${STATUS} failingStreak=${STREAK}"

  if [ "$STREAK" != "-1" ] && [ "$STREAK" -ge "$RESTART_AFTER" ] 2>/dev/null; then
    echo "[watchdog] ⚠ Health streak ${STREAK} ≥ ${RESTART_AFTER} — alerting (no auto-restart: PR#872 fixes root cause)."
    # DAK-9890: auto-restart removed — it masked the access_info zombie leak
    # root cause (PR#872). Alert so humans can investigate and act deliberately.
    # Re-enable auto-restart here only after confirming root cause is fixed in prod.
    tg_send "⚠️ <b>[Platform] dakera healthcheck degraded — investigation required</b>
Host: $(hostname)
Reason: healthcheck failingStreak=${STREAK} ≥ threshold ${RESTART_AFTER}
Health: ${STATUS}
Root cause: access_info zombie leak — see https://github.com/Dakera-AI/dakera/pull/872
Action: Check <code>docker exec dakera curl -s localhost:3000/admin/storage/stats | jq .hot_count</code>
If memory pressure: <code>docker restart ${CONTAINER}</code> (manual, deliberate)"
  fi

  # ── Memory threshold check ───────────────────────────────────────────────
  MEM_PCT=$(get_mem_pct)
  if [ -n "$MEM_PCT" ] && [ "$MEM_PCT" -ge "$MEM_ALERT_PCT" ] 2>/dev/null; then
    MEM_ALERT_COUNT=$((MEM_ALERT_COUNT + 1))
    CYCLES_SINCE_LAST=$((CYCLE - LAST_MEM_ALERT_CYCLE))
    # Alert on first occurrence and every 10 cycles thereafter to avoid spam
    if [ "$MEM_ALERT_COUNT" -eq 1 ] || [ "$CYCLES_SINCE_LAST" -ge 10 ]; then
      LAST_MEM_ALERT_CYCLE=$CYCLE
      echo "[watchdog] ⚠ Memory at ${MEM_PCT}% ≥ ${MEM_ALERT_PCT}% threshold."
      tg_send "🧠 <b>[Platform] dakera memory pressure warning</b>
Host: $(hostname)
Memory: ${MEM_PCT}% of container limit
Threshold: ${MEM_ALERT_PCT}%
Action: Monitor — container will auto-restart if health fails (streak ≥ ${RESTART_AFTER})
Tip: <code>docker restart ${CONTAINER}</code> reclaims heap pages if approaching 100%."
    fi
  else
    MEM_ALERT_COUNT=0
  fi
done
