#!/usr/bin/env python3
"""
Plaud -> Notion/Calendar sync watcher.

Listens (IMAP IDLE) on a Gmail inbox for Plaud AutoFlow "summary ready" emails.
On each new one, it invokes Claude Code headlessly (`claude -p`) with a task
prompt so Claude fetches the recording via the Plaud MCP and files it into
Notion + creates Google Calendar events.

Config comes from environment variables (see the .env / systemd EnvironmentFile).

Requires:  pip install imapclient
Auth model: the machine must already be logged in with `claude login` (your Max
account) and have the Plaud, Notion, and Google Calendar MCPs added at USER scope.
"""
import os
import re
import sys
import json
import time
import email
import logging
import smtplib
import subprocess
from email.header import decode_header, make_header
from email.message import EmailMessage
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from imapclient import IMAPClient

# ---------- config (from environment) ----------
IMAP_HOST     = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_PORT     = int(os.environ.get("IMAP_PORT", "993"))
IMAP_USER     = os.environ["IMAP_USER"]
IMAP_PASSWORD = os.environ["IMAP_PASSWORD"]          # Gmail APP password (not your normal password)
IMAP_FOLDER   = os.environ.get("IMAP_FOLDER", "INBOX")
PLAUD_SENDER  = os.environ.get("PLAUD_SENDER", "")   # substring of the From address, e.g. "plaud.ai"
SUBJECT_MATCH = os.environ.get("SUBJECT_MATCH", "")  # optional extra substring filter on the subject
CLAUDE_BIN    = os.environ.get("CLAUDE_BIN", "claude")
MODEL         = os.environ.get("MODEL", "sonnet")
PROMPT_FILE   = os.environ["PROMPT_FILE"]
WORKDIR       = os.environ.get("WORKDIR", os.getcwd())
LOG_FILE      = os.environ.get("LOG_FILE", "plaud-sync.log")
STATE_FILE    = os.environ.get("STATE_FILE", "processed.json")
RUNS_LOG      = os.environ.get("RUNS_LOG", "runs.jsonl")
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT", "600"))
# Server names here must match how you ran `claude mcp add <name> ...`.
ALLOWED_TOOLS = os.environ.get(
    "ALLOWED_TOOLS", "mcp__plaud__*,mcp__notion__*,mcp__google-calendar__*"
)
RETRY_DELAY  = int(os.environ.get("RETRY_DELAY", "120"))  # seconds before the single failure retry
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")         # failure alerts go here; empty disables
SMTP_HOST    = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.environ.get("SMTP_PORT", "465"))
IDLE_TIMEOUT = 29 * 60  # re-issue IDLE before the ~30-min server cutoff

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("plaud-sync")

PLAUD_URL_RE = re.compile(r"https?://[^\s\"'>]*plaud[^\s\"'>]*", re.IGNORECASE)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_state(processed):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(processed), f)
    os.replace(tmp, STATE_FILE)


def decode_str(raw):
    if raw is None:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def get_body_text(msg):
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype in ("text/plain", "text/html") and "attachment" not in disp:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode(part.get_content_charset() or "utf-8", "replace"))
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(msg.get_content_charset() or "utf-8", "replace"))
        except Exception:
            pass
    return "\n".join(parts)


def build_prompt(base_prompt, subject, plaud_link, received):
    ctx = (
        "\n\n---\n## The recording to process (from the triggering email)\n"
        f"- Email subject: {subject}\n"
        f"- Plaud link found in email: {plaud_link or 'none found — locate by title + recency'}\n"
        f"- Email received (UTC): {received}\n"
        "Use the Plaud MCP to locate THIS recording (by the link's ID if present, otherwise the "
        "most recent recording whose title matches the subject), then follow the steps above.\n"
    )
    return base_prompt + ctx


def run_claude(prompt):
    cmd = [
        CLAUDE_BIN, "-p", prompt,
        "--model", MODEL,
        "--allowedTools", ALLOWED_TOOLS,
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
    ]
    log.info("Invoking Claude (model=%s) ...", MODEL)
    try:
        res = subprocess.run(
            cmd, cwd=WORKDIR, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        log.error("Claude run timed out after %ss", CLAUDE_TIMEOUT)
        return {"ok": False, "stdout": "", "stderr": f"timeout after {CLAUDE_TIMEOUT}s"}
    if res.returncode != 0:
        log.error("Claude exited %s. stderr tail:\n%s", res.returncode, (res.stderr or "")[-2000:])
    return {"ok": res.returncode == 0, "stdout": res.stdout or "", "stderr": res.stderr or ""}


def extract_report(text):
    """Pull the JSON report object out of the model's final text.

    The prompt demands raw JSON, but tolerate markdown fences or stray prose
    around it so runs.jsonl stays machine-parseable either way.
    """
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


def notify_failure(uid, subject, run):
    """Email a failure alert via the same Gmail account the watcher reads (best-effort)."""
    if not NOTIFY_EMAIL:
        return
    msg = EmailMessage()
    msg["From"] = IMAP_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = f"[plaud-sync] sync FAILED: {subject[:120]}"
    msg.set_content(
        f"Both attempts failed for uid={uid}.\n"
        f"Subject: {subject}\n\n"
        f"stderr tail:\n{(run['stderr'] or '(empty)')[-1500:]}\n\n"
        f"Details are in {RUNS_LOG}. To replay: mark the email unread, remove the uid from "
        f"{STATE_FILE}, and restart the service — or use /replay-note in Claude Code."
    )
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.login(IMAP_USER, IMAP_PASSWORD)
            smtp.send_message(msg)
        log.info("Failure alert emailed to %s", NOTIFY_EMAIL)
    except Exception as e:
        log.warning("Could not email failure alert: %s", e)


def log_run(uid, subject, plaud_link, run, attempt=1):
    """Append one structured record per run to RUNS_LOG (JSON Lines). Returns overall ok."""
    summary, cost, duration_ms, is_error = None, None, None, None
    try:
        data = json.loads(run["stdout"])       # `claude -p --output-format json` result envelope
        summary = data.get("result")           # the model's final text = the JSON report we asked for
        cost = data.get("total_cost_usd")
        duration_ms = data.get("duration_ms")
        is_error = data.get("is_error")
    except (json.JSONDecodeError, TypeError):
        summary = (run["stdout"] or "")[-2000:] or None    # fallback: raw stdout tail
    report = extract_report(summary)
    ok = run["ok"] and not is_error
    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "uid": uid,
        "subject": subject,
        "plaud_link": plaud_link,
        "ok": ok,
        "attempt": attempt,
        "cost_usd": cost,
        "duration_ms": duration_ms,
        "report": report,                       # parsed JSON report (None if unparseable)
        "summary": None if report else summary, # raw text kept only when parsing failed
        "error": None if ok else ((run["stderr"] or "")[-1000:] or "see summary"),
    }
    with open(RUNS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return ok


def process_message(server, uid, base_prompt, processed):
    raw = server.fetch([uid], ["RFC822"])[uid][b"RFC822"]
    msg = email.message_from_bytes(raw)
    subject = decode_str(msg.get("Subject"))
    received = datetime.now(timezone.utc).isoformat()
    body = get_body_text(msg)
    m = PLAUD_URL_RE.search(body)
    plaud_link = m.group(0) if m else None
    log.info("New Plaud email uid=%s subject=%r link=%s", uid, subject, plaud_link)

    prompt = build_prompt(base_prompt, subject, plaud_link, received)
    run = run_claude(prompt)
    ok = log_run(uid, subject, plaud_link, run)     # append a structured record to runs.jsonl
    if not ok:
        # One delayed retry: transient API/MCP failures are common enough to be worth a second
        # attempt, and the prompt's create-or-update idempotency makes the retry safe.
        log.warning("Run failed for uid=%s — retrying once in %ss", uid, RETRY_DELAY)
        time.sleep(RETRY_DELAY)
        run = run_claude(prompt)
        ok = log_run(uid, subject, plaud_link, run, attempt=2)
    log.info("Run recorded (ok=%s) -> %s", ok, RUNS_LOG)

    # Mark seen + record UID regardless, so we never reprocess in a loop.
    try:
        server.add_flags([uid], [b"\\Seen"])
    except Exception as e:
        log.warning("Could not mark uid=%s seen: %s", uid, e)
    processed.add(uid)
    save_state(processed)
    if not ok:
        log.error("uid=%s did NOT sync cleanly — see %s and re-run manually if needed.", uid, RUNS_LOG)
        notify_failure(uid, subject, run)


def search_and_process(server, base_prompt, processed):
    criteria = ["UNSEEN"]
    if PLAUD_SENDER:
        criteria += ["FROM", PLAUD_SENDER]
    for uid in server.search(criteria):
        if uid in processed:
            continue
        if SUBJECT_MATCH:
            hdr = server.fetch([uid], ["BODY.PEEK[HEADER.FIELDS (SUBJECT)]"])
            subj = decode_str(email.message_from_bytes(
                hdr[uid][b"BODY[HEADER.FIELDS (SUBJECT)]"]).get("Subject"))
            if SUBJECT_MATCH.lower() not in subj.lower():
                continue
        process_message(server, uid, base_prompt, processed)


def main():
    with open(PROMPT_FILE) as f:
        base_prompt = f.read()
    processed = load_state()
    log.info("Starting Plaud sync watcher for %s (folder=%s)", IMAP_USER, IMAP_FOLDER)

    while True:
        try:
            with IMAPClient(IMAP_HOST, port=IMAP_PORT, use_uid=True, ssl=True) as server:
                server.login(IMAP_USER, IMAP_PASSWORD)
                server.select_folder(IMAP_FOLDER)
                log.info("Connected. Clearing any backlog, then idling.")
                search_and_process(server, base_prompt, processed)  # handle anything already waiting
                while True:
                    server.idle()
                    responses = server.idle_check(timeout=IDLE_TIMEOUT)
                    server.idle_done()
                    if responses:
                        search_and_process(server, base_prompt, processed)
        except Exception as e:
            log.exception("Connection/loop error (%s) — reconnecting in 15s", e)
            time.sleep(15)


if __name__ == "__main__":
    main()
