#!/bin/bash
# wedged-runner-watchdog.sh — DAK-7528
# Detects GitHub Actions self-hosted runners that are busy=true with no active job
# (the "wedged" state after a cgroup-OOM kills a worker without releasing the runner).
#
# Wedged signature (all three must be true):
#   1. Runner shows busy=true AND online in GitHub API
#   2. Zero CI runs are in_progress across the runner-sharing repos
#   3. At least one CI run has been queued for > STALL_THRESHOLD_MIN minutes
#
# On detection: SSHes into the affected host and restarts all actions.runner.* services,
# then sends a Telegram alert. Rate-limited by RESTART_COOLDOWN_SECS.
#
# Normally invoked by the runner-wedged-watchdog.yml GitHub Actions workflow (runs every
# 10min on ubuntu-latest). Can also be run manually from any machine with GH_TOKEN + SSH.
#
# Environment variables:
#   GH_TOKEN                  — GitHub PAT with repo/runner read access
#   TELEGRAM_BOT_TOKEN        — Telegram bot token (optional, skips alert if unset)
#   TELEGRAM_CHAT_ID          — Telegram chat ID (optional)
#   ARM_RUNNER_IP             — IP of ARM runner host (default: 168.119.60.30)
#   X64_RUNNER_IP             — IP of x64 runner host (default: 178.104.227.173)
#   SSH_KEY_PATH              — Path to SSH private key (default: ~/.ssh/id_ed25519)
#   STALL_THRESHOLD_MIN       — Queue stall before acting, in minutes (default: 10)
#   RESTART_COOLDOWN_SECS     — Minimum seconds between restarts (default: 600)
#   DRY_RUN                   — If "true", detect and alert but do not restart (default: false)
#   STATE_DIR                 — Where to store rate-limit state (default: /var/lib/runner-watchdog)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load credentials from .credentials file if available (agent ops pattern)
for _f in "${SCRIPT_DIR}/../../../.credentials" "${HOME}/.dakera.env"; do
  [[ -f "$_f" ]] && { set -a; source "$_f"; set +a; break; }
done

ARM_RUNNER_IP="${ARM_RUNNER_IP:-168.119.60.30}"
X64_RUNNER_IP="${X64_RUNNER_IP:-178.104.227.173}"
SSH_KEY_PATH="${SSH_KEY_PATH:-${HOME}/.ssh/id_ed25519}"
STALL_THRESHOLD_MIN="${STALL_THRESHOLD_MIN:-10}"
RESTART_COOLDOWN_SECS="${RESTART_COOLDOWN_SECS:-600}"
DRY_RUN="${DRY_RUN:-false}"
STATE_DIR="${STATE_DIR:-/var/lib/runner-watchdog}"
LOG_FILE="${LOG_FILE:-/var/log/wedged-runner-watchdog.log}"
DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
NOW=$(date +%s)

# Repos that share the same self-hosted runner fleet
RUNNER_REPOS=(
  "dakera-ai/dakera"
  "dakera-ai/dakera-cli"
  "dakera-ai/dakera-mcp"
  "dakera-ai/dakera-bench"
)

SSH_OPTS="-i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o ServerAliveInterval=5"

mkdir -p "$STATE_DIR" 2>/dev/null || true

log() {
  local msg="$DATE $*"
  echo "$msg"
  echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
  logger -t wedged-runner-watchdog "$*" 2>/dev/null || true
}

tg_alert() {
  [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]] && return 0
  curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":\"${TELEGRAM_CHAT_ID}\",\"text\":\"$1\"}" >/dev/null 2>&1 || true
}

gh_api() {
  if [[ -n "${GH_TOKEN:-}" ]]; then
    curl -sf -H "Authorization: Bearer ${GH_TOKEN}" \
         -H "Accept: application/vnd.github+json" \
         "https://api.github.com/$1" 2>/dev/null
  else
    gh api "$1" 2>/dev/null
  fi
}

log "START — checking wedged-runner condition"

# ── Phase 1: Find busy runners ──────────────────────────────────────────────
declare -A BUSY_MAP  # runner_name → host_ip
for REPO in "${RUNNER_REPOS[@]}"; do
  while IFS=$'\t' read -r NAME STATUS BUSY; do
    [[ "$STATUS" == "online" && "$BUSY" == "true" ]] || continue
    if echo "$NAME" | grep -qi "x64\|amd64\|x86"; then
      BUSY_MAP["$NAME"]="$X64_RUNNER_IP"
    else
      BUSY_MAP["$NAME"]="$ARM_RUNNER_IP"
    fi
    log "  BUSY: ${NAME} → ${BUSY_MAP[$NAME]} (from ${REPO})"
  done < <(gh_api "repos/${REPO}/actions/runners" | \
    jq -r '.runners[] | [.name, .status, (.busy | tostring)] | @tsv' 2>/dev/null || true)
done

if [ "${#BUSY_MAP[@]}" -eq 0 ]; then
  log "No busy runners — fleet healthy"
  exit 0
fi

log "Found ${#BUSY_MAP[@]} busy runner(s): ${!BUSY_MAP[*]}"

# ── Phase 2: Check for in_progress jobs ─────────────────────────────────────
IN_PROGRESS=0
for REPO in "${RUNNER_REPOS[@]}"; do
  COUNT=$(gh run list -R "$REPO" --status in_progress \
    --json databaseId --jq 'length' 2>/dev/null || echo 0)
  [ "$COUNT" -gt 0 ] && log "  in_progress in ${REPO}: ${COUNT}"
  IN_PROGRESS=$((IN_PROGRESS + COUNT))
done

if [ "$IN_PROGRESS" -gt 0 ]; then
  log "Runners legitimately busy — ${IN_PROGRESS} job(s) in_progress, no action"
  exit 0
fi

# ── Phase 3: Check queue stall duration ─────────────────────────────────────
OLDEST_STALL_SECS=0
for REPO in "${RUNNER_REPOS[@]}"; do
  while IFS= read -r CREATED_AT; do
    [[ -z "$CREATED_AT" ]] && continue
    QUEUED_TS=$(date -d "$CREATED_AT" +%s 2>/dev/null || echo "$NOW")
    STALL_SECS=$(( NOW - QUEUED_TS ))
    [ "$STALL_SECS" -gt "$OLDEST_STALL_SECS" ] && OLDEST_STALL_SECS=$STALL_SECS
  done < <(gh run list -R "$REPO" --status queued \
    --json createdAt --jq '.[].createdAt' 2>/dev/null || true)
done

OLDEST_STALL_MIN=$(( OLDEST_STALL_SECS / 60 ))
STALL_THRESHOLD_SECS=$(( STALL_THRESHOLD_MIN * 60 ))

if [ "$OLDEST_STALL_SECS" -lt "$STALL_THRESHOLD_SECS" ]; then
  log "Queue stall ${OLDEST_STALL_MIN}min < threshold ${STALL_THRESHOLD_MIN}min — transient, no action"
  exit 0
fi

# ── WEDGED CONDITION CONFIRMED ───────────────────────────────────────────────
log "WEDGED: ${#BUSY_MAP[@]} runner(s) busy=true, 0 in_progress, stalled ${OLDEST_STALL_MIN}min"

if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN — detection complete, skipping restart"
  tg_alert "⚠️ [Platform] Wedged Runner Detected (DRY RUN)%0A%0ARunners: ${!BUSY_MAP[*]}%0AStalled: ${OLDEST_STALL_MIN}min%0ANo restart performed."
  exit 0
fi

# ── Rate-limit check ────────────────────────────────────────────────────────
COOLDOWN_FILE="${STATE_DIR}/last-wedged-restart"
LAST_RESTART=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)
if [ $(( NOW - LAST_RESTART )) -lt "$RESTART_COOLDOWN_SECS" ]; then
  REMAINING=$(( RESTART_COOLDOWN_SECS - (NOW - LAST_RESTART) ))
  log "Cooldown active (${REMAINING}s remaining) — alerting only"
  tg_alert "⚠️ [Platform] Wedged Runner Still Stuck — cooldown active (${REMAINING}s). Stalled ${OLDEST_STALL_MIN}min. Manual check may be needed."
  exit 0
fi

# ── Restart wedged runners ───────────────────────────────────────────────────
declare -A RESTARTED
declare -A FAILED

# Deduplicate by host (restart each host only once even if multiple runners are wedged)
declare -A HOSTS_SEEN
for RUNNER_NAME in "${!BUSY_MAP[@]}"; do
  HOST="${BUSY_MAP[$RUNNER_NAME]}"
  [[ -n "${HOSTS_SEEN[$HOST]:-}" ]] && continue
  HOSTS_SEEN["$HOST"]=1

  log "SSH restart: ${RUNNER_NAME} on ${HOST}"
  if ssh $SSH_OPTS "root@${HOST}" '
    echo "Pre-restart runner states:"
    systemctl list-units "actions.runner.*" --no-pager --no-legend | head -20
    echo "Restarting..."
    systemctl restart "actions.runner.*" 2>/dev/null || true
    sleep 8
    echo "Post-restart runner states:"
    ACTIVE=$(systemctl list-units "actions.runner.*" --no-pager --no-legend --state=active 2>/dev/null | wc -l)
    TOTAL=$(systemctl list-units "actions.runner.*" --no-pager --no-legend 2>/dev/null | wc -l)
    systemctl list-units "actions.runner.*" --no-pager --no-legend
    echo "Result: ${ACTIVE}/${TOTAL} active"
  ' 2>&1; then
    RESTARTED["$HOST"]="$RUNNER_NAME"
    log "Restarted ${RUNNER_NAME} on ${HOST}"
  else
    FAILED["$HOST"]="$RUNNER_NAME"
    log "FAILED restart for ${RUNNER_NAME} on ${HOST}"
  fi
done

echo "$NOW" > "$COOLDOWN_FILE"

# ── Alerts ───────────────────────────────────────────────────────────────────
if [ "${#RESTARTED[@]}" -gt 0 ]; then
  HEALED_LIST=$(for h in "${!RESTARTED[@]}"; do echo " • ${RESTARTED[$h]} (${h})"; done | paste -sd '%0A')
  tg_alert "🔄 [Platform] Wedged Runner Auto-Healed%0A%0ACondition: ${#BUSY_MAP[@]} runner(s) busy=true, 0 in_progress, stalled ${OLDEST_STALL_MIN}min%0ARestarted:%0A${HEALED_LIST}%0A%0ARunners reconnect in ~30s."
  log "AUTO-HEALED: ${#RESTARTED[@]} host(s) restarted"
fi

if [ "${#FAILED[@]}" -gt 0 ]; then
  FAILED_LIST=$(for h in "${!FAILED[@]}"; do echo " • ${FAILED[$h]} (${h})"; done | paste -sd '%0A')
  tg_alert "🔴 [Platform ALERT] Wedged Runner Restart FAILED%0A%0ARunners: ${!BUSY_MAP[*]}%0AStalled: ${OLDEST_STALL_MIN}min%0AFAILED hosts:%0A${FAILED_LIST}%0A%0AManual SSH restart required."
  log "RESTART FAILED: ${#FAILED[@]} host(s)"
  exit 1
fi
