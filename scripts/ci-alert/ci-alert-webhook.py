#!/usr/bin/env python3
"""
CI Failure Alerting Webhook — DAK-4572

Listens for GitHub workflow_run events. When a workflow fails on main/master,
creates a Paperclip issue assigned to the repo owner agent, or adds a comment
to an existing open issue (cooldown / dedup).

Required env vars:
  PAPERCLIP_API_URL     e.g. https://paperclip.dakera.ai
  PAPERCLIP_COMPANY_ID  UUID of the Dakera company
  PAPERCLIP_API_KEY     Bearer token for agent-authenticated calls
  GITHUB_WEBHOOK_SECRET HMAC secret set in the GitHub org webhook config

Optional:
  CI_ALERT_PORT   listening port (default: 8765)
"""

import hashlib
import hmac
import json
import logging
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────────────────────

PAPERCLIP_API_URL = os.environ.get("PAPERCLIP_API_URL", "")
PAPERCLIP_COMPANY_ID = os.environ.get("PAPERCLIP_COMPANY_ID", "")
PAPERCLIP_API_KEY = os.environ.get("PAPERCLIP_API_KEY", "")
GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
PORT = int(os.environ.get("CI_ALERT_PORT", "8765"))

# Repo name → assignee agent UUID
REPO_OWNER = {
    "dakera":          "76c16e17-0a79-416b-8d37-c8f912d99312",  # CTO
    "dakera-bench":    "76c16e17-0a79-416b-8d37-c8f912d99312",  # CTO
    "dakera-mcp":      "76c16e17-0a79-416b-8d37-c8f912d99312",  # CTO
    "dakera-cli":      "8854bc33-d856-4ac5-b462-2da1f79c785a",  # QA
    "dakera-py":       "2b03a819-473d-4ab8-8db7-2cefc9b818f9",  # SDK Lead
    "dakera-js":       "2b03a819-473d-4ab8-8db7-2cefc9b818f9",  # SDK Lead
    "dakera-rs":       "2b03a819-473d-4ab8-8db7-2cefc9b818f9",  # SDK Lead
    "dakera-go":       "2b03a819-473d-4ab8-8db7-2cefc9b818f9",  # SDK Lead
    "dakera-deploy":   "01347741-1538-434f-89ef-6bcb95b480a6",  # Platform
}

WATCHED_BRANCHES = {"main", "master"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("ci-alert")


# ── Validation ─────────────────────────────────────────────────────────────────

def _check_env() -> None:
    missing = [k for k in ("PAPERCLIP_API_URL", "PAPERCLIP_COMPANY_ID", "PAPERCLIP_API_KEY")
               if not os.environ.get(k)]
    if missing:
        log.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)
    if not GITHUB_WEBHOOK_SECRET:
        log.warning("GITHUB_WEBHOOK_SECRET not set — webhook signature verification disabled")


# ── HMAC verification ──────────────────────────────────────────────────────────

def _verify_signature(body: bytes, sig_header: str) -> bool:
    if not GITHUB_WEBHOOK_SECRET:
        return True
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(sig_header, expected)


# ── Paperclip CLI helpers ──────────────────────────────────────────────────────

def _paperclip(*args) -> dict | list | None:
    """Run npx paperclipai <args> and return parsed JSON, or None on error.

    --api-base and --api-key are subcommand-level options and must follow
    the subcommand (e.g. 'issue list --api-base URL'), not the top-level binary.
    """
    cmd = [
        "npx", "paperclipai",
        *args,
        "--api-base", PAPERCLIP_API_URL,
        "--api-key", PAPERCLIP_API_KEY,
        "--json",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log.error("paperclipai %s failed: %s", args[0] if args else "", result.stderr.strip())
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        log.error("paperclipai %s timed out", args[0] if args else "")
        return None
    except json.JSONDecodeError as e:
        log.error("paperclipai returned invalid JSON: %s", e)
        return None
    except Exception as e:
        log.error("paperclipai subprocess error: %s", e)
        return None


_OPEN_STATUSES = {"todo", "in_progress", "in_review"}

def find_open_ci_issue(repo: str, assignee_id: str) -> str | None:
    """Return ID of an existing open CI FAILURE issue for this repo, or None."""
    prefix = f"CI FAILURE: {repo}"
    issues = _paperclip(
        "issue", "list",
        "--company-id", PAPERCLIP_COMPANY_ID,
    )
    if not isinstance(issues, list):
        return None
    for issue in issues:
        if issue.get("status", "") not in _OPEN_STATUSES:
            continue
        if issue.get("title", "").startswith(prefix) and issue.get("assigneeAgentId") == assignee_id:
            return issue.get("id")
    return None


def create_ci_issue(repo: str, workflow: str, run_url: str, ts: str, assignee_id: str) -> bool:
    title = f"CI FAILURE: {repo} {workflow} — main branch red"
    description = (
        f"## CI Failure Detected\n\n"
        f"- **Repo:** `dakera-ai/{repo}`\n"
        f"- **Workflow:** `{workflow}`\n"
        f"- **Branch:** main\n"
        f"- **Failed run:** {run_url}\n"
        f"- **Detected at:** {ts} UTC\n\n"
        f"Please investigate and fix the failing workflow. "
        f"If multiple failures are listed below in comments, they share the same root cause."
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
    if result:
        log.info("Created Paperclip issue for %s: %s", repo, title)
        return True
    return False


def comment_on_issue(issue_id: str, repo: str, workflow: str, run_url: str, ts: str) -> bool:
    body = (
        f"**Additional failure on `{repo}`:** `{workflow}` — {ts} UTC\n"
        f"Run: {run_url}"
    )
    result = _paperclip("issue", "comment", issue_id, "--body", body)
    if result is not None:
        log.info("Added comment to issue %s for %s", issue_id, repo)
        return True
    return False


# ── HTTP handler ───────────────────────────────────────────────────────────────

class WebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info(fmt, *args)

    def _respond(self, code: int, body: str = "") -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, "ok")
        else:
            self._respond(404, "not found")

    def do_POST(self):
        if self.path != "/webhook":
            self._respond(404, "not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # Verify HMAC signature
        sig = self.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(body, sig):
            log.warning("Rejected webhook: invalid signature from %s", self.client_address[0])
            self._respond(401, "invalid signature")
            return

        event = self.headers.get("X-GitHub-Event", "")
        if event == "ping":
            log.info("GitHub ping received — webhook connected successfully")
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

        self._handle_workflow_run(payload)
        self._respond(200, "ok")

    def _handle_workflow_run(self, payload: dict) -> None:
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

        if action != "completed" or conclusion != "failure":
            return
        if branch not in WATCHED_BRANCHES:
            return
        if repo not in REPO_OWNER:
            log.info("Repo %s not in owner map — skipping", repo)
            return

        assignee = REPO_OWNER[repo]
        existing_id = find_open_ci_issue(repo, assignee)
        if existing_id:
            comment_on_issue(existing_id, repo, workflow, run_url, ts)
        else:
            create_ci_issue(repo, workflow, run_url, ts, assignee)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _check_env()
    log.info(
        "CI alert webhook starting on :%d (repos: %s)",
        PORT, ", ".join(sorted(REPO_OWNER)),
    )
    server = HTTPServer(("0.0.0.0", PORT), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
