#!/usr/bin/env bash
# Rebuild Dakera's full-text indexes once after upgrading a deployment that
# holds v0.11.108 data to v0.12.0.
#
# Why: full-text indexes built by v0.11 are re-analysed under v0.12's text
# analysis. Until this runs, keyword search and keyword-style recall can
# return nothing. It only rebuilds derived search indexes; memories are not
# touched. Fresh v0.12.0 installs do not need it, and from v0.12.1 the server
# applies it automatically.
#
# Environment:
#   DAKERA_URL        API base URL, e.g. https://dakera.example.com
#                     (default: http://localhost:3000)
#   DAKERA_ADMIN_KEY  key with global admin scope (falls back to
#                     DAKERA_ROOT_API_KEY, the key in docker/.env)
#   DAKERA_NAMESPACE  optional: rebuild one namespace instead of all
#
# Usage:
#   DAKERA_URL=https://dakera.example.com DAKERA_ADMIN_KEY=... \
#     scripts/post-upgrade-reindex.sh
set -euo pipefail

url="${DAKERA_URL:-http://localhost:3000}"
url="${url%/}"
key="${DAKERA_ADMIN_KEY:-${DAKERA_ROOT_API_KEY:-}}"
namespace="${DAKERA_NAMESPACE:-}"

if [ -z "$key" ]; then
  echo "error: set DAKERA_ADMIN_KEY (or DAKERA_ROOT_API_KEY) to a global admin key" >&2
  exit 2
fi

if [ -n "$namespace" ]; then
  if ! [[ "$namespace" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "error: DAKERA_NAMESPACE may only contain letters, digits, '_', '.' and '-'" >&2
    exit 2
  fi
  body="{\"namespace\":\"${namespace}\",\"rebuild\":true}"
else
  body='{"rebuild":true}'
fi

echo "Rebuilding full-text indexes at ${url} (${namespace:-all namespaces})..." >&2

response="$(mktemp)"
trap 'rm -f "$response"' EXIT

status="$(curl -sS -o "$response" -w '%{http_code}' -X POST "${url}/admin/fulltext/reindex" \
  -H "x-api-key: ${key}" -H 'content-type: application/json' -d "$body")"

cat "$response"
echo

if [ "$status" != "200" ]; then
  echo "error: the server answered HTTP ${status}" >&2
  exit 1
fi

echo "Done. Check with a keyword search: POST ${url}/v1/namespaces/<ns>/fulltext/search" >&2
