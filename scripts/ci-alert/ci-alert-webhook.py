#!/usr/bin/env python3
"""
CI Failure Alerting Webhook — DAK-4572

Listens for GitHub workflow_run events. When a workflow fails on main/master,
creates a Paperclip issue assigned to the repo owner agent, or adds a comment
to an existing open issue (cooldown / dedup).

Design:
- Respond 200 to GitHub immediately (background thread for Paperclip calls).
- Cooldown uses a local JSON cache file instead of querying the slow issue-list
  API -- avoids the 2-minute GET /issues query on every event.
- Cache TTL: COOLDOWN_DAYS (default 7). After TTL expires, a new issue is created.

Required env vars:
  PAPERCLIP_API_URL     e.g. http://localhost:3100
  PAPERCLIP_COMPANY_ID  UUID of the Dakera company
  PAPERCLIP_API_KEY     Bearer token for agent-authenticated calls
  GITHUB_WEBHOOK_SECRET HMAC secret set in the GitHub org webhook config
  CI_AGENT_IDS          JSON object mapping repo name -> assignee agent UUID
                        e.g. '{"dakera":"<uuid>","dakera-py":"<uuid>"}'
                        Store this as a GitHub Secret or in /etc/ci-alert/env.

Optional:
  CI_ALERT_PORT     listening port (default: 8765)
  CI_CACHE_FILE     JSON cache path (default: /var/lib/ci-alert/cache.json)
  COOLDOWN_DAYS     days before a new issue is created for same repo (default: 7)
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────────────────────

PAPERCLIP_API_URL = os.environ.get("PAPERCLIP_API_URL", "")
PAPERCLIP_COMPANY_ID = os.environ.get("PAPERCLIP_COMPANY_ID", "")
PAPERCLIP_API_KEY = os.environ.get("PAPERCLIP_API_KEY", "")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
PORT = int(os.environ.get("CI_ALERT_PORT", "8765"))
CACHE_FILE = os.environ.get("CI_CACHE_FILE", "/var/lib/ci-alert/cache.json")
COOLDOWN_SECS = int(os.environ.get("COOLDOWN_DAYS", "7")) * 86400

# Repo name -> assignee agent UUID — loaded from CI_AGENT_IDS env var at startup.
# Never hardcode UUIDs here; store them in /etc/ci-alert/env or a GitHub Secret.
REPO_OWNER: dict = {}

WATCHED_BRANCHES = {"main", "master"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("ci-alert")

# Thread lock for cache file access
_cache_lock = threading.Lock()


# ── Validation ─────────────────────────────────────────────────────────────────

def _check_env():
    missing = [k for k in ("PAPERCLIP_API_URL", "PAPERCLIP_COMPANY_ID", "PAPERCLIP_API_KEY", "CI_AGENT_IDS")
               if not os.environ.get(k)]
    if missing:
        log.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)
    if not GITHUB_WEBHOOK_SECRET:
        log.warning("GITHUB_WEBHOOK_SECRET not set -- webhook signature verification disabled")
    _load_agent_ids()
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)


def _load_agent_ids():
    """Populate REPO_OWNER from the CI_AGENT_IDS JSON env var."""
    raw = os.environ.get("CI_AGENT_IDS", "")
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("CI_AGENT_IDS is not valid JSON: %s", e)
        sys.exit(1)
    if not isinstance(mapping, dict) or not mapping:
        log.error("CI_AGENT_IDS must be a non-empty JSON object")
        sys.exit(1)
    REPO_OWNER.update(mapping)
    log.info("Loaded %d repo->agent mappings from CI_AGENT_IDS", len(REPO_OWNER))


# ── HMAC verification ──────────────────────────────────────────────────────────

def _verify_signature(body, sig_header):
    if not GITHUB_WEBHOOK_SECRET:
        return True
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig_header, expected)


# ── Local cache (cooldown) ─────────────────────────────────────────────────────

def _load_cache():
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(cache):
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp, CACHE_FILE)


def get_cached_issue(repo):
    """Return (issue_id, created_ts) if an active cooldown entry exists, else (None, None)."""
    with _cache_lock:
        cache = _load_cache()
    entry = cache.get(repo)
    if not entry:
        return None, None
    age = time.time() - entry.get("created_at", 0)
    if age > COOLDOWN_SECS:
        return None, None
    return entry.get("issue_id"), entry.get("created_at")


def set_cached_issue(repo, issue_id):
    """Store a new issue ID in the cache for this repo."""
    with _cache_lock:
        cache = _load_cache()
        cache[repo] = {"issue_id": issue_id, "created_at": time.time()}
        _save_cache(cache)


# ── Paperclip CLI helpers ──────────────────────────────────────────────────────

def _paperclip(*args):
    """Run paperclipai <args> and return parsed JSON, or None on error."""
    cmd = [
        "paperclipai",
        *args,
        "--api-base", PAPERCLIP_API_URL,
        "--api-key", PAPERCLIP_API_KEY,
        "--json",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            env={**os.environ, "PATH": "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin"},
        )
        if result.returncode != 0:
            log.error("paperclipai %s failed: %s", args[0] if args else "", result.stderr[:500])
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        log.error("paperclipai %s timed out (60s)", args[0] if args else "")
        return None
    except json.JSONDecodeError as e:
        log.error("paperclipai returned invalid JSON: %s", e)
        return None
    except Exception as e:
        log.error("paperclipai subprocess error: %s", e)
        return None


def create_ci_issue(repo, workflow, run_url, ts, assignee_id):
    title = "CI FAILURE: " + repo + " " + workflow + " -- main branch red"
    description = (
        "## CI Failure Detected\n\n"
        "- **Repo:** `dakera-ai/" + repo + "`\n"
        "- **Workflow:** `" + workflow + "`\n"
        "- **Branch:** main\n"
        "- **Failed run:** " + run_url + "\n"
        "- **Detected at:** " + ts + " UTC\n\n"
        "Please investigate and fix the failing workflow. "
        "Additional failures for the same repo will be added as comments below."
    )
    result = _paperclip(
        "issue", "create",
        "--company-id", PAPERCLIP_COMPANY_ID,
        "--title", title,
        "--description", description,
        "--assignee-agent-id", assignee_id,
        "--status", "todo",
        "--priority", "high",
    )
    if result and result.get("id"):
        issue_id = result["id"]
        log.info("Created Paperclip issue %s for %s: %s", issue_id, repo, title)
        set_cached_issue(repo, issue_id)
        return issue_id
    return None


def comment_on_issue(issue_id, repo, workflow, run_url, ts):
    body = (
        "**Additional failure:** `" + workflow + "` -- " + ts + " UTC\n"
        "Run: " + run_url
    )
    result = _paperclip("issue", "comment", issue_id, "--body", body)
    if result is not None:
        log.info("Added comment to issue %s for %s (%s)", issue_id, repo, workflow)
        return True
    return False


def process_ci_failure(repo, workflow, run_url, ts):
    """Background worker: find or create Paperclip issue for a CI failure."""
    assignee = REPO_OWNER[repo]
    try:
        existing_id, _ = get_cached_issue(repo)
        if existing_id:
            log.info("Cooldown hit for %s -- commenting on issue %s", repo, existing_id)
            comment_on_issue(existing_id, repo, workflow, run_url, ts)
        else:
            log.info("No active issue for %s -- creating new one", repo)
            create_ci_issue(repo, workflow, run_url, ts, assignee)
    except Exception as e:
        log.error("process_ci_failure error for %s: %s", repo, e)


# ── HTTP handler ───────────────────────────────────────────────────────────────

class WebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info(fmt, *args)

    def _respond(self, code, body=""):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        try:
            self.wfile.write(body.encode())
        except BrokenPipeError:
            pass

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, "ok")
        elif self.path == "/cache":
            with _cache_lock:
                cache = _load_cache()
            self._respond(200, json.dumps(cache, indent=2))
        else:
            self._respond(404, "not found")

    def do_POST(self):
        if self.path != "/webhook":
            self._respond(404, "not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        sig = self.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(body, sig):
            log.warning("Rejected: invalid signature from %s", self.client_address[0])
            self._respond(401, "invalid signature")
            return

        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            log.info("GitHub ping received -- webhook connected successfully")
            self._respond(200, "pong")
            return

        if event != "workflow_run":
            self._respond(200, "ignored")
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, "invalid json")
            return

        action = payload.get("action", "")
        run = payload.get("workflow_run", {})
        conclusion = run.get("conclusion", "")
        branch = run.get("head_branch", "")
        repo = payload.get("repository", {}).get("name", "")
        workflow = run.get("name", "unknown")
        run_url = run.get("html_url", "")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

        log.info(
            "workflow_run: repo=%s action=%s conclusion=%s branch=%s workflow=%s",
            repo, action, conclusion, branch, workflow,
        )

        # Respond to GitHub immediately -- Paperclip call happens in background thread
        self._respond(200, "ok")

        if (
            action == "completed"
            and conclusion == "failure"
            and branch in WATCHED_BRANCHES
            and repo in REPO_OWNER
        ):
            t = threading.Thread(
                target=process_ci_failure,
                args=(repo, workflow, run_url, ts),
                daemon=True,
            )
            t.start()


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _check_env()
    log.info(
        "CI alert webhook starting on :%d (cache: %s, cooldown: %dd)",
        PORT, CACHE_FILE, COOLDOWN_SECS // 86400,
    )
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
