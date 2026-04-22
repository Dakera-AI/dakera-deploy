#!/bin/bash
# Automated Docker disk cleanup for self-hosted GitHub Actions runners
# Deployed by: Platform agent (HB116, 2026-04-22)
# Installed at: /usr/local/bin/docker-cleanup.sh
# Managed by: docker-cleanup.timer (runs daily at 02:00 UTC)
#
# Root cause this prevents: Docker volumes + build cache accumulate unchecked,
# causing OOM/disk-full failures on CI (incident: HB115, 2026-04-22).

set -euo pipefail

THRESHOLD=75
LOG="/var/log/docker-cleanup.log"

DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] CHECK disk=${DISK_USAGE}% threshold=${THRESHOLD}%" >> "$LOG"

if [ "$DISK_USAGE" -gt "$THRESHOLD" ]; then
    BEFORE=$(df -h / | tail -1 | awk '{print $3}')
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] CLEANUP START used=${BEFORE}" >> "$LOG"

    # Remove stopped containers, dangling images, unused networks
    PRUNE_OUT=$(docker system prune -f 2>&1)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] system prune: ${PRUNE_OUT}" >> "$LOG"

    # Remove unused volumes (not referenced by any running container)
    VOL_OUT=$(docker volume prune -f 2>&1)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] volume prune: ${VOL_OUT}" >> "$LOG"

    # Prune build cache older than 24h
    CACHE_OUT=$(docker builder prune -f --filter until=24h 2>&1)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] builder prune: ${CACHE_OUT}" >> "$LOG"

    AFTER_USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
    AFTER=$(df -h / | tail -1 | awk '{print $3}')
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] CLEANUP END disk=${AFTER_USAGE}% used=${AFTER}" >> "$LOG"
else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] OK no cleanup needed" >> "$LOG"
fi
