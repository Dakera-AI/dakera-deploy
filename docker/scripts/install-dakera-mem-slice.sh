#!/usr/bin/env bash
# =============================================================================
# install-dakera-mem-slice.sh  (FW-b5ad5a7f / DAK-9814)
# -----------------------------------------------------------------------------
# Installs a systemd slice that applies a cgroup-v2 memory.high (soft limit) to
# the Dakera container. Referenced by docker-compose.yml via `cgroup_parent`.
#
# Why: the Dakera container's RSS did not return to baseline after allocation
# peaks and pegged the 8G hard cap, exhausting host swap (same precondition as
# the 2026-07-11 UI-hang). DAK-9814 set memory.high=7G with an 8G hard wall.
# DAK-9890 raised the hard wall to 12G (fleet load reached 7.14GiB under full
# agent load); the soft limit follows at 10G. memory.high lets the kernel
# throttle & reclaim the cgroup gracefully BEFORE the 12G hard wall triggers
# an OOM kill. The root fix (mimalloc returning pages to the OS) is
# MIMALLOC_PURGE_DELAY=0 in the compose env; this slice is the safety net.
#
# Idempotent. Requires root (systemd unit + daemon-reload). Persists across
# reboots and CI redeploys (deploys scp only docker-compose.yml, not units).
# =============================================================================
set -euo pipefail

MEM_HIGH="${DAKERA_MEM_HIGH:-10G}"  # DAK-9890: raised 7G→10G to match new 12G hard limit
UNIT=/etc/systemd/system/dakera-mem.slice

if [[ $EUID -ne 0 ]]; then
  echo "Re-executing under sudo..." >&2
  exec sudo -E "$0" "$@"
fi

# cgroup v2 is required for MemoryHigh on a slice.
if [[ "$(stat -fc %T /sys/fs/cgroup/ 2>/dev/null)" != "cgroup2fs" ]]; then
  echo "ERROR: host is not on cgroup v2; memory.high slice unsupported." >&2
  exit 1
fi

cat > "$UNIT" <<EOF
# Managed by install-dakera-mem-slice.sh (FW-b5ad5a7f / DAK-9814).
# Soft memory backpressure for the Dakera container; see docker-compose.yml
# cgroup_parent: dakera-mem.slice.
[Unit]
Description=Dakera container memory slice (soft memory.high backpressure)
Before=docker.service

[Slice]
MemoryAccounting=yes
MemoryHigh=${MEM_HIGH}
EOF

systemctl daemon-reload
systemctl start dakera-mem.slice

echo "✅ dakera-mem.slice installed with MemoryHigh=${MEM_HIGH}"
systemctl show dakera-mem.slice -p MemoryHigh -p MemoryAccounting
