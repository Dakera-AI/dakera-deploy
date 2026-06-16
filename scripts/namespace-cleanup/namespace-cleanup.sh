#!/bin/bash
# Stale namespace cleanup for Dakera production server
# Deployed by: Platform agent (DAK-6099, 2026-05-31)
#
# Root cause this prevents: Smoke tests, bench preflight scripts, and one-off
# verification agents create temporary namespaces and never clean them up,
# causing unbounded storage growth. Incident: DAK-6099 (34 stale namespaces,
# 320+ vectors accumulated before first cleanup).
#
# Stale patterns deleted:
#   _dakera_agent_smoke-<timestamp>        LME/LoCoMo preflight smoke runs
#   _dakera_agent_smoke-test-<ticket>      Smoke test namespaces
#   _dakera_agent_*-smoke-test             Smoke test suffix variant
#   _dakera_agent_*-smoke                  Short smoke suffix
#   _dakera_agent_*-preflight-*            Bench preflight timing/check
#   _dakera_agent_*-probe                  Probe/diagnostic namespaces
#   _dakera_agent_<dak|ce>-*-verify-*      One-time verification namespaces
#   test-*                                 Bare test namespaces
#   sanity-*                               Bare sanity-check namespaces
#
# Preserved namespaces (never touched by this script):
#   _dakera_sessions                       Core: session storage
#   _dakera_namespace_configs              Core: namespace config storage
#   _dakera_fulltext_indices               Core: fulltext index storage
#   _dakera_background_metrics             Core: background metrics
#   _dakera_agent_<stable-agent-id>        Production agents (no tickets/timestamps)
#   _dakera_agent_room-<name>              Squad rooms
#   _dakera_agent_tg-user-*               Telegram user context

set -euo pipefail

DAKERA_API_URL="${DAKERA_API_URL:?DAKERA_API_URL must be set}"
DAKERA_API_KEY="${DAKERA_API_KEY:?DAKERA_API_KEY must be set}"
DRY_RUN="${DRY_RUN:-0}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

is_stale() {
    local ns="$1"
    # Bare test namespaces (no _dakera_ prefix)
    if [[ "$ns" =~ ^test- ]] || [[ "$ns" =~ ^sanity- ]]; then return 0; fi
    # Must be an agent namespace to be stale
    [[ "$ns" == _dakera_agent_* ]] || return 1
    local agent="${ns#_dakera_agent_}"
    # Smoke runs: smoke-<digits> (timestamp-based)
    [[ "$agent" =~ ^smoke-[0-9]+ ]] && return 0
    # Smoke tests: smoke-test-*
    [[ "$agent" =~ ^smoke-test- ]] && return 0
    # Smoke suffix: *-smoke-test or *-smoke
    [[ "$agent" =~ -smoke-test$ ]] && return 0
    [[ "$agent" =~ -smoke$ ]] && return 0
    # Preflight: *-preflight-*
    [[ "$agent" =~ -preflight- ]] && return 0
    # Probe: *-probe
    [[ "$agent" =~ -probe$ ]] && return 0
    # Verify: dak*-verify-* or ce*-verify-*
    [[ "$agent" =~ ^dak[0-9]+-verify- ]] && return 0
    [[ "$agent" =~ ^ce[0-9]+-verify- ]] && return 0
    # Verify suffix: *-verify-<timestamp/date>
    [[ "$agent" =~ -verify-[0-9]+ ]] && return 0
    return 1
}

log "=== Dakera Namespace Cleanup ==="
log "Target: ${DAKERA_API_URL}"
[ "$DRY_RUN" = "1" ] && log "DRY_RUN=1 — no deletions will be performed"

# Fetch all namespaces
namespaces=$(curl -sf -H "X-API-Key: ${DAKERA_API_KEY}" "${DAKERA_API_URL}/v1/namespaces" | jq -r '.namespaces[]')
total=$(echo "$namespaces" | wc -l | tr -d ' ')
log "Found ${total} namespaces total"

deleted=0
skipped=0
failed=0

while IFS= read -r ns; do
    if is_stale "$ns"; then
        if [ "$DRY_RUN" = "1" ]; then
            info=$(curl -sf -H "X-API-Key: ${DAKERA_API_KEY}" "${DAKERA_API_URL}/v1/namespaces/${ns}" 2>/dev/null | jq -r '.vector_count // 0')
            log "DRY_RUN WOULD DELETE: ${ns} (${info} vectors)"
            deleted=$((deleted + 1))
        else
            result=$(curl -s -w "\n%{http_code}" -H "X-API-Key: ${DAKERA_API_KEY}" \
                -X DELETE "${DAKERA_API_URL}/v1/namespaces/${ns}" 2>/dev/null)
            http_code=$(echo "$result" | tail -1)
            body=$(echo "$result" | head -n -1)
            vectors=$(echo "$body" | jq -r '.vectors_deleted // 0' 2>/dev/null || echo "0")
            if [ "$http_code" = "200" ]; then
                log "DELETED: ${ns} (${vectors} vectors)"
                deleted=$((deleted + 1))
            else
                err=$(echo "$body" | jq -r '.error // .message // "unknown"' 2>/dev/null || echo "unknown")
                log "FAILED[${http_code}]: ${ns} — ${err}"
                failed=$((failed + 1))
            fi
        fi
    else
        skipped=$((skipped + 1))
    fi
done <<< "$namespaces"

log "=== Summary: ${deleted} deleted, ${skipped} kept, ${failed} failed ==="

# Exit non-zero if any deletions failed
[ "$failed" -eq 0 ]
