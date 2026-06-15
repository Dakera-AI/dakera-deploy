#!/usr/bin/env bash
# hetzner.sh — Hetzner Cloud helper for Dakera Playground operations
# Uses hcloud CLI (installed on first call). HCLOUD_TOKEN must be in env.
set -euo pipefail

SSH_KEY_NAME="ops-dakera-ai"
SSH_PUBLIC_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO+69Mv++aOAjMyHWmmtYXp6O31t1jwQXFt9OHzqIoN2 ops@dakera.ai"

_ensure_hcloud() {
    if ! command -v hcloud &>/dev/null; then
        echo "[hetzner.sh] Installing hcloud CLI..." >&2
        curl -fsSL https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-amd64.tar.gz \
            | tar xz -C /usr/local/bin hcloud
    fi
}

_ensure_ssh_key() {
    local fingerprint
    fingerprint=$(ssh-keygen -E md5 -lf /dev/stdin <<< "$SSH_PUBLIC_KEY" \
        | awk '{print $2}' | sed 's/MD5://')
    local existing_id
    existing_id=$(hcloud ssh-key list -o json \
        | python3 -c "import sys,json; keys=json.load(sys.stdin); \
          m=[k['id'] for k in keys if k['fingerprint']=='$fingerprint']; \
          print(m[0] if m else '')")
    if [ -n "$existing_id" ]; then
        echo "$existing_id"
        return
    fi
    hcloud ssh-key create --name "$SSH_KEY_NAME" --public-key "$SSH_PUBLIC_KEY" \
        --output format="{{ .ID }}"
}

cmd_provision() {
    # Usage: provision <name> <type> <location> <image> <cloud-init-file>
    local name="${1:?name required}"
    local type="${2:-cpx31}"
    local location="${3:-fsn1}"
    local image="${4:-ubuntu-24.04}"
    local user_data_file="${5:-}"

    _ensure_ssh_key >/dev/null

    local extra_args=()
    [ -n "$user_data_file" ] && extra_args+=(--user-data-from-file "$user_data_file")

    local existing_id
    existing_id=$(hcloud server describe "$name" --output format="{{ .ID }}" 2>/dev/null || echo "")
    if [ -n "$existing_id" ]; then
        echo "[hetzner.sh] Server '$name' already exists (id: $existing_id)" >&2
        hcloud server describe "$name" --output format="{{ .PublicNet.IPv4.IP }}"
        return 0
    fi

    echo "[hetzner.sh] Creating $name ($type @ $location / $image)..." >&2
    hcloud server create \
        --name "$name" \
        --type "$type" \
        --image "$image" \
        --location "$location" \
        --ssh-key "$SSH_KEY_NAME" \
        --label "env=playground" \
        --label "managed_by=dakera-platform" \
        "${extra_args[@]}" \
        --output format="{{ .Server.PublicNet.IPv4.IP }}"
    echo "[hetzner.sh] Server created." >&2
}

cmd_wait_ssh() {
    # Usage: wait-ssh <ip> [max_attempts]
    local ip="${1:?ip required}"
    local max="${2:-36}"
    echo "[hetzner.sh] Waiting for SSH on $ip..." >&2
    for i in $(seq 1 "$max"); do
        if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
            root@"$ip" "echo ok" 2>/dev/null; then
            echo "[hetzner.sh] SSH ready." >&2
            return 0
        fi
        echo "[hetzner.sh] Attempt $i/$max..." >&2
        sleep 10
    done
    echo "[hetzner.sh] TIMEOUT: SSH unavailable after ${max} attempts." >&2
    return 1
}

cmd_wait_cloud_init() {
    # Usage: wait-cloud-init <ip> <ssh-key-file> [max_attempts]
    local ip="${1:?ip required}"
    local key="${2:?key file required}"
    local max="${3:-40}"
    echo "[hetzner.sh] Waiting for cloud-init to finish on $ip..." >&2
    for i in $(seq 1 "$max"); do
        local status
        status=$(ssh -i "$key" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            root@"$ip" "cloud-init status 2>/dev/null || echo unknown" 2>/dev/null || echo "unreachable")
        echo "[hetzner.sh] Attempt $i/$max — cloud-init: $status" >&2
        case "$status" in
            *done*) echo "[hetzner.sh] Cloud-init complete." >&2; return 0 ;;
            *error*) echo "[hetzner.sh] Cloud-init errored." >&2; return 1 ;;
        esac
        sleep 15
    done
    echo "[hetzner.sh] TIMEOUT: cloud-init did not finish." >&2
    return 1
}

cmd_ip() {
    local name="${1:?name required}"
    hcloud server describe "$name" --output format="{{ .PublicNet.IPv4.IP }}"
}

cmd_delete() {
    local name="${1:?name required}"
    local id
    id=$(hcloud server describe "$name" --output format="{{ .ID }}" 2>/dev/null || echo "")
    if [ -z "$id" ]; then
        echo "[hetzner.sh] Server '$name' not found." >&2
        return 0
    fi
    echo "[hetzner.sh] Deleting $name (id: $id)..." >&2
    hcloud server delete "$name"
    echo "[hetzner.sh] Deleted." >&2
}

cmd_list() {
    hcloud server list -o columns=id,name,ipv4,type,status,datacenter
}

_ensure_hcloud

CMD="${1:-help}"
shift 2>/dev/null || true

case "$CMD" in
    provision)        cmd_provision "$@" ;;
    wait-ssh)         cmd_wait_ssh "$@" ;;
    wait-cloud-init)  cmd_wait_cloud_init "$@" ;;
    ip)               cmd_ip "$@" ;;
    delete)           cmd_delete "$@" ;;
    list)             cmd_list ;;
    help|*)
        echo "Usage: HCLOUD_TOKEN=<tok> $0 <cmd> [args]"
        echo "Commands:"
        echo "  provision <name> [type=cpx31] [loc=fsn1] [image=ubuntu-24.04] [cloud-init-file]"
        echo "  wait-ssh <ip> [max_attempts=36]"
        echo "  wait-cloud-init <ip> <key-file> [max_attempts=40]"
        echo "  ip <name>"
        echo "  delete <name>"
        echo "  list"
        exit 1
        ;;
esac
