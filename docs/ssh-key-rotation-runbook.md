# SSH Key Rotation Runbook

**Secret:** `DEPLOY_SSH_KEY` in `dakera-ai/dakera-deploy`

**Affects workflows:**
- `playground-proxy-deploy.yml` → playground server (5.75.177.31)
- `playground-monitor-deploy.yml` → playground server (5.75.177.31)
- `deploy-production.yml` → production server (178.104.45.161)

Both servers share the same `DEPLOY_SSH_KEY` secret. Rotate the key on **all servers at once**.

---

## When to rotate

- Workflow fails with `Permission denied (publickey)` or `exit 255`
- SSH key is suspected compromised (unauthorized access, leaked key material)
- Preventive rotation (recommended every 90 days)
- After removing a team member with server access

---

## Step 1 — Generate new ed25519 keypair

```bash
ssh-keygen -t ed25519 -C 'deploy@dakera-deploy' -f /tmp/deploy_key -N ''
# Creates: /tmp/deploy_key (private) and /tmp/deploy_key.pub (public)
```

---

## Step 2 — Authorize the new key on all servers

Add the public key to **each server's** `authorized_keys`. Keep the old key until Step 3 is done
(removing it before updating the GH secret causes a deploy outage window).

```bash
PLAYGROUND_IP="5.75.177.31"
PROD_IP="178.104.45.161"

# Playground server
cat /tmp/deploy_key.pub | ssh root@${PLAYGROUND_IP} \
  'cat >> ~/.ssh/authorized_keys && echo "added to playground"'

# Production server
cat /tmp/deploy_key.pub | ssh root@${PROD_IP} \
  'cat >> ~/.ssh/authorized_keys && echo "added to production"'
```

If you don't have direct SSH access and need to use the existing DEPLOY_SSH_KEY:

```bash
cat /tmp/deploy_key.pub | ssh -i ~/.ssh/existing_deploy_key root@${PLAYGROUND_IP} \
  'cat >> ~/.ssh/authorized_keys'
cat /tmp/deploy_key.pub | ssh -i ~/.ssh/existing_deploy_key root@${PROD_IP} \
  'cat >> ~/.ssh/authorized_keys'
```

---

## Step 3 — Update the GitHub secret

```bash
gh secret set DEPLOY_SSH_KEY --repo dakera-ai/dakera-deploy < /tmp/deploy_key
```

Verify the secret was updated (check the `Updated at` timestamp):

```bash
gh secret list -R dakera-ai/dakera-deploy | grep DEPLOY_SSH_KEY
```

---

## Step 4 — Test SSH connectivity from local machine

```bash
PLAYGROUND_IP="5.75.177.31"
PROD_IP="178.104.45.161"

ssh -i /tmp/deploy_key -o BatchMode=yes -o ConnectTimeout=5 root@${PLAYGROUND_IP} echo "playground OK"
ssh -i /tmp/deploy_key -o BatchMode=yes -o ConnectTimeout=5 root@${PROD_IP} echo "production OK"
```

Both must print `OK`. If either fails with `Permission denied`, re-check Step 2 for that server.

---

## Step 5 — Verify deploy workflows succeed

Trigger a manual test run for each affected workflow and confirm success:

```bash
# Playground proxy deploy
gh workflow run playground-proxy-deploy.yml -R dakera-ai/dakera-deploy --ref main \
  -f reason="SSH key rotation verification"

# Playground monitor deploy
gh workflow run playground-monitor-deploy.yml -R dakera-ai/dakera-deploy --ref main \
  -f reason="SSH key rotation verification"

# Production deploy (requires a version input — use current prod version to test SSH, no-op deploy)
gh workflow run deploy-production.yml -R dakera-ai/dakera-deploy --ref main \
  -f version="current"
```

Watch the runs:

```bash
gh run watch -R dakera-ai/dakera-deploy
```

All three workflows must reach `success` with `✅ SSH connectivity verified` in their logs.

---

## Cleanup

After all workflows pass, remove the old key from each server and clean up the temp key files:

```bash
# Remove old public key from servers (replace OLD_KEY_FRAGMENT with first 20 chars of old pubkey)
OLD_KEY_FRAGMENT="ssh-ed25519 AAAAC3NzaC1..."

ssh -i /tmp/deploy_key root@${PLAYGROUND_IP} \
  "sed -i '/${OLD_KEY_FRAGMENT}/d' ~/.ssh/authorized_keys && echo 'removed from playground'"
ssh -i /tmp/deploy_key root@${PROD_IP} \
  "sed -i '/${OLD_KEY_FRAGMENT}/d' ~/.ssh/authorized_keys && echo 'removed from production'"

# Remove temp key files
rm /tmp/deploy_key /tmp/deploy_key.pub
```

---

## Quick-reference (tl;dr)

```
1. ssh-keygen -t ed25519 -C 'deploy@dakera-deploy' -f /tmp/deploy_key -N ''
2. cat /tmp/deploy_key.pub | ssh root@5.75.177.31 'cat >> ~/.ssh/authorized_keys'
   cat /tmp/deploy_key.pub | ssh root@178.104.45.161 'cat >> ~/.ssh/authorized_keys'
3. gh secret set DEPLOY_SSH_KEY --repo dakera-ai/dakera-deploy < /tmp/deploy_key
4. ssh -i /tmp/deploy_key root@5.75.177.31 echo OK && ssh -i /tmp/deploy_key root@178.104.45.161 echo OK
5. gh workflow run playground-proxy-deploy.yml -R dakera-ai/dakera-deploy --ref main
   gh workflow run deploy-production.yml -R dakera-ai/dakera-deploy --ref main -f version=current
```

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Permission denied (publickey,password)` | Key mismatch — GH secret doesn't match `authorized_keys` | Start from Step 2 |
| `Connection refused` | Server firewall blocking port 22 | Check Hetzner Cloud Firewall rules |
| `Connection timed out` | Server unreachable | Check server is running via Hetzner console |
| `Warning: Permanently added` then fail | `known_hosts` mismatch (server IP changed) | Run `ssh-keyscan -H <IP>` to update |

---

*Maintained by Platform. Last updated: 2026-06-17 (DAK-6947).*
