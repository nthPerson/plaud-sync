#!/usr/bin/env python3
"""
Weekly digest for the Plaud Synced Notes database.

Runs headless Claude Code (Notion MCP only) to query the week's notes and compose
a digest, then emails it via the same Gmail account the watcher reads. Invoked by
the plaud-digest.timer systemd unit; config comes from the shared .env.
"""
import json
import os
import re
import smtplib
import subprocess
import sys
from email.message import EmailMessage

IMAP_USER      = os.environ["IMAP_USER"]
IMAP_PASSWORD  = os.environ["IMAP_PASSWORD"]
NOTIFY_EMAIL   = os.environ["NOTIFY_EMAIL"]        # digest recipient (same as failure alerts)
CLAUDE_BIN     = os.environ.get("CLAUDE_BIN", "claude")
MODEL          = os.environ.get("MODEL", "sonnet")
WORKDIR        = os.environ.get("WORKDIR", os.path.dirname(os.path.abspath(__file__)))
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "600"))
SMTP_HOST      = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.environ.get("SMTP_PORT", "465"))


def extract_json(text):
    """Same tolerant JSON extraction the watcher uses for run reports."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        candidate = m.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def send(subject, body):
    msg = EmailMessage()
    msg["From"] = IMAP_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.login(IMAP_USER, IMAP_PASSWORD)
        smtp.send_message(msg)


def main():
    with open(os.path.join(WORKDIR, "weekly-digest-prompt.txt")) as f:
        prompt = f.read()
    try:
        res = subprocess.run(
            [CLAUDE_BIN, "-p", prompt,
             "--model", MODEL,
             "--allowedTools", "mcp__notion__*",
             "--output-format", "json"],
            cwd=WORKDIR, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        send("[plaud-sync] weekly digest FAILED", f"Claude run timed out after {CLAUDE_TIMEOUT}s.")
        sys.exit(1)

    report, cost = None, None
    try:
        envelope = json.loads(res.stdout)
        report = extract_json(envelope.get("result"))
        cost = envelope.get("total_cost_usd")
    except (json.JSONDecodeError, TypeError):
        pass

    if res.returncode != 0 or not report or "body" not in report:
        send(
            "[plaud-sync] weekly digest FAILED",
            f"exit={res.returncode}\n\nstderr tail:\n{(res.stderr or '(empty)')[-1500:]}"
            f"\n\nstdout tail:\n{(res.stdout or '(empty)')[-1500:]}",
        )
        sys.exit(1)

    footer = f"\n\n--\nplaud-sync weekly digest · run cost ${cost:.2f}" if cost else ""
    send(report.get("subject") or "Plaud weekly digest", report["body"] + footer)
    print(f"Digest sent to {NOTIFY_EMAIL} (cost ${cost or 0:.2f})")


if __name__ == "__main__":
    main()
