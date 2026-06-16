# Dakera Playground Sandbox Proxy (DAK-6713)

A lightweight HTTP proxy that sits between the public playground frontend and
the Dakera engine, enforcing **per-session** sandbox limits that Nginx's per-IP
rules cannot express.

```
browser (dakera.ai/playground)
   │  https
   ▼
Nginx :443  ── per-IP rate limit, TLS, MinIO block (deploy PR#180)
   │  /v1/* (and all non-health API)
   ▼
sandbox-proxy :3100  ── per-SESSION rate / cap / TTL / allow-list / CORS
   │  + injects server-side root API key
   ▼
Dakera engine :3000
```

The proxy is **pure Node.js stdlib — zero npm dependencies** (no install layer,
tiny container, no supply-chain surface).

## Enforced limits (acceptance criteria)

| # | Limit | Default | Env var |
|---|-------|---------|---------|
| 1 | Rate limit per session | 10 req / 60s sliding window | `SANDBOX_RATE_LIMIT_PER_MIN` |
| 2 | Memory cap per session | 50 (batch items counted) | `SANDBOX_MEMORY_CAP` |
| 3 | Session TTL | 30 min auto-expiry | `SANDBOX_SESSION_TTL_SEC` |
| 4 | Endpoint allow-list | deny-by-default | (see `allowlist.js`) |
| 5 | CORS | `dakera.ai`, `www.dakera.ai`, `playground.dakera.ai` | `SANDBOX_ALLOWED_ORIGINS` |
| 6 | Health endpoint | `GET /health` | — |

Extra hardening: server-side root-key injection (clients send `playground-demo`,
never the real key), a per-IP live-session ceiling (`SANDBOX_MAX_SESSIONS_PER_IP`,
default 20) so the caps can't be bypassed by rotating the session header, and a
request body size cap (`SANDBOX_MAX_BODY_BYTES`, default 256 KB).

## Sessions

Identified by the `X-Playground-Session` header (`pg_…`). When a client does not
send a valid one, the proxy mints a session and returns it in the
`X-Playground-Session` response header (CORS-exposed) for the client to persist
and resend. Header-less requests fall back to an IP-keyed bucket, so the caps
always apply. The per-IP ceiling above bounds header-rotation abuse; Nginx's
per-IP req/s ceiling remains the first line of defence.

## Per-session isolation (DAK-6757)

Every public session authenticates as the same `playground-demo` agent_id, so
without isolation any session could recall what any other session stored — a
cross-session PII leak (QA finding DAK-6753). The proxy fixes this in
`namespace.js`:

- **Request:** every `agent_id` in the forwarded JSON body (top-level and nested
  batch items) is rewritten to a private namespace
  `playground-demo-<sha256(sessionId)[:12]>`. An omitted `agent_id` is forced to
  the namespace too, so it can never fall back to the shared default. The
  namespace is deterministic, so a session always recalls its own stores.
- **Response:** the engine's response is buffered and the namespace is swapped
  back to the client's original `agent_id`, so the isolation is invisible to the
  frontend (no client-visible change to the `agent_id` format). `accept-encoding`
  is dropped on namespaced requests so the response body is plaintext-rewritable.

Header-less clients are isolated by their IP-bucket session key, so the caps and
namespace still apply.

## Allowed endpoints

Only the read/store operations the playground scenarios use (store, recall,
search, route, knowledge-graph reads). **Everything else is rejected with 403**
— all `/admin/*`, any `DELETE`, `forget`/`bulk-delete`/`bulk-update`, `import`,
`export`, namespace + vector mutation, and cross-agent consolidation. See
`allowlist.js` for the exact table.

## Response headers

- `X-Playground-Session` — the session id (persist + resend it)
- `X-Sandbox-Rate-Remaining` — calls left in the current window
- `X-Sandbox-Memory-Remaining` — memories left before the cap (on cap rejection)
- `Retry-After` — seconds until the rate window frees (on 429)

## Run / test

```bash
npm start        # node index.js
npm test         # node --test  (20 unit + integration tests, zero deps)
```

## Deploy

Built and wired automatically by `docker/docker-compose.playground.yml`
(service `sandbox-proxy`) and routed by `docker/nginx-playground.conf`
(`location /` → `127.0.0.1:3100`). Provisioned by `playground-provision.yml`
(DAK-6706). Requires `DAKERA_ROOT_API_KEY` in the deploy `.env`.
