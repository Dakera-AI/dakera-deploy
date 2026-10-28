# Dakera Cloud: the engine server

How the server behind Dakera Cloud is set up. The console (`cloud.dakera.ai`) is a
Cloudflare Pages project in `Dakera-AI/dakera-cloud`; this page covers the engine
it talks to. Design and reasons: `dakera-cloud/docs/SCOPE.md` §6.

```text
SDK / CLI / MCP ──▶ api.dakera.ai ─────────┐
                                           ├─▶ Cloudflare Tunnel ─▶ cloudflared ×2 ─▶ dakera:3000
console Functions ─▶ engine-origin.dakera.ai ┘        (outbound only, no open ports)
  (Access service token)
staff ─▶ ops.dakera.ai (Access SSO) ─────────────────────────────────▶ grafana:3000
```

## Once

1. **Tunnel.** On any machine with `cloudflared` logged in to the dakera.ai zone:

   ```bash
   cloudflared tunnel create dakera-cloud            # writes <tunnel-id>.json
   cloudflared tunnel route dns dakera-cloud api.dakera.ai
   cloudflared tunnel route dns dakera-cloud engine-origin.dakera.ai
   cloudflared tunnel route dns dakera-cloud ops.dakera.ai
   ```

   Copy `<tunnel-id>.json` to `docker/cloudflared/` on the server and
   `docker/cloudflared/config.yml.example` to `config.yml` with the id filled in.
   Both are git-ignored.

2. **Access.** Zero Trust → Access → Applications:
   - `engine-origin.dakera.ai`: one policy, *Service Auth*, allowing a service
     token made for the console. Its id and secret become the console's
     `ENGINE_ACCESS_CLIENT_ID` / `ENGINE_ACCESS_CLIENT_SECRET`.
   - `ops.dakera.ai`: staff emails, SSO.

3. **Zone settings for `api.dakera.ai`.** SDKs are not browsers, so:
   - Bot Fight Mode **off** (it challenges API clients); use a custom WAF rule
     instead if bots show up.
   - Cache rule: *Bypass cache* for `api.dakera.ai` and `engine-origin.dakera.ai`.
   - WAF custom rule, a second fence behind the tunnel's own 404s: block
     `http.host in {"api.dakera.ai" "engine-origin.dakera.ai"} and
     (starts_with(http.request.uri.path, "/admin") or
     starts_with(http.request.uri.path, "/metrics") or
     starts_with(http.request.uri.path, "/internal"))`.
   - Rate limiting rule (the free plan has one, on a 10 s period): 100 requests /
     10 s per IP on `api.dakera.ai`, as a flood guard; per-project limits are the
     engine's.

4. **Engine image with tenant mode.** Cloud needs an engine release with tenant
   mode (`/v1/tenants/{tenant}/keys`). Set `DAKERA_IMAGE` in `.env` to it.

5. **Provisioner key.** With the stack up, mint the console's engine key on the
   server itself (the root key never leaves it):

   ```bash
   curl -s http://127.0.0.1:3000/admin/keys \
     -H "Authorization: Bearer $DAKERA_ROOT_API_KEY" -H 'Content-Type: application/json' \
     -d '{"name":"cloud-provisioner","scope":"admin","namespaces":["_dakera_agent_dc*","dc*"]}'
   ```

   Its `key` becomes the console's `ENGINE_PROVISIONER_KEY` secret. It can create
   and revoke tenant keys inside the `dc` family and nothing else.

## Run

```bash
cd docker
docker compose -f docker-compose.yml -f docker-compose.cloud.yml --profile monitoring up -d
```

Check from outside:

```bash
curl -s https://api.dakera.ai/health                    # 200
curl -s -o /dev/null -w '%{http_code}\n' https://api.dakera.ai/metrics      # 404
curl -s -o /dev/null -w '%{http_code}\n' https://engine-origin.dakera.ai/health  # 403 without the token
```

## Limits to keep in mind

| Limit | Where | What we do |
| --- | --- | --- |
| 125 s proxy read timeout (524) | Cloudflare | `DAKERA_REQUEST_TIMEOUT=90` answers first |
| 100 MB request body | Cloudflare (Free/Pro) | The engine's own limit is 10 MB (`DAKERA_MAX_BODY_SIZE`) |
| Rerank cost per recall | Engine CPU | `DAKERA_RERANK_MAX_CANDIDATES=30` |
| 100,000 Functions requests / day | Pages (free) | The console only; SDK traffic never touches Functions |

## Rotating

- **Tunnel credentials:** `cloudflared tunnel token` / re-create, replace the json,
  `docker compose ... up -d cloudflared`.
- **Provisioner key:** mint a new one (step 5), set it on the Pages project,
  redeploy, then revoke the old one with `DELETE /admin/keys/{id}`. Console keys
  minted by the old provisioner keep working.
