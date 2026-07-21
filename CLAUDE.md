# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-purpose automation: a Plaud AutoFlow recording gets transcribed → Plaud emails a
notification → this watcher notices → it shells out to **headless Claude Code**, which uses MCP
tools to file the note into Notion and create any calendar events the note implies.

```
Plaud AutoFlow ──email──▶ Gmail (IMAP IDLE)
                              │
                    plaud_watcher.py  ── detects UNSEEN mail FROM plaud.ai
                              │
                    subprocess: claude -p "<prompt-file> + email context"
                              │
                    ┌─────────┴──────────┬────────────────────┐
              Plaud MCP            Notion MCP        Google Calendar MCP
           (fetch recording)   (create DB page)     (create dated events)
                              │
                    runs.jsonl  ◀── structured record per run (cost, ok, summary)
```

## The one architectural fact that matters

**`plaud_watcher.py` contains no business logic. `plaud-sync-prompt.txt` is the program.**

The Python is dumb plumbing: connect, detect, extract a subject + any Plaud URL, shell out, log.
Every decision that shapes output — the Notion database, the Area/Type/Project/Tags taxonomy and
what each option means, the calendar rules, the JSON report format — lives in the prompt file.

To change what the automation *does*, edit `plaud-sync-prompt.txt`. Touching the Python is almost
always the wrong move. Note that the prompt is read once at startup, so a prompt edit still requires
a service restart.

## Runtime layout

| Path | Role |
|---|---|
| `plaud_watcher.py` | IMAP IDLE loop + `claude -p` invoker. ~235 lines, no deps beyond `imapclient`. |
| `plaud-sync-prompt.txt` | The actual task definition handed to headless Claude. |
| `.env` | All config. Loaded by systemd via `EnvironmentFile=`. Contains a Gmail **app password**. |
| `plaud-sync.service` | Repo copy of the unit. **Drifted from the installed one — see gotchas.** |
| `processed.json` | Set of handled IMAP UIDs. Idempotency guard. |
| `runs.jsonl` | One JSON record per Claude run: `ok`, `cost_usd`, `duration_ms`, `report` (parsed JSON report; `summary` holds raw text only when parsing fails). |
| `project-routing.json` | Project → Notion destination registry for the distribution step. URLs currently unfilled. |
| `plaud-sync.log` | Human log (also goes to journald). |
| `.venv/` | Python 3.12 venv holding `IMAPClient==3.1.0`. **The service runs this interpreter.** |

## Commands

```bash
# service (installed as a system unit, enabled at boot, runs as user robert)
systemctl status plaud-sync
sudo systemctl restart plaud-sync          # required after editing plaud_watcher.py OR .env
journalctl -u plaud-sync -f                # live
tail -f plaud-sync.log

# run the watcher in the foreground (stop the service first, or it double-processes)
sudo systemctl stop plaud-sync
set -a; source .env; set +a; .venv/bin/python plaud_watcher.py

# inspect run history
python3 -c "import json;[print(f\"{r['time'][:16]} ok={r['ok']} \${r['cost_usd'] or 0:.3f} {r['subject'][:60]}\") for r in map(json.loads,open('runs.jsonl'))]"

# exercise the prompt against one recording WITHOUT touching email (the main dev loop)
claude -p "$(cat plaud-sync-prompt.txt)

---
## The recording to process
- Email subject: <subject>
- Plaud link found in email: none found — locate by title + recency
- Email received (UTC): $(date -u +%FT%TZ)" \
  --model sonnet \
  --allowedTools 'mcp__plaud__*,mcp__notion__*,mcp__claude_ai_Google_Calendar__*' \
  --output-format json

# reprocess an email the watcher already consumed: drop its UID from processed.json,
# mark it unread in Gmail, then restart the service.
```

There are no tests, no build, and no linter configured.

## Gotchas that will bite you

**The service must run the venv interpreter, not system Python** (system Python has no `imapclient`).
Both the repo unit and the installed unit at `/etc/systemd/system/plaud-sync.service` now use
`ExecStart=/home/robert/plaud-sync/.venv/bin/python …` and are byte-identical, so reinstalling is a
clean `sudo cp plaud-sync.service /etc/systemd/system/ && sudo systemctl daemon-reload`. If they ever
drift again, the venv path is the correct one — never "fix" it back to `/usr/bin/python3`. If the
venv is rebuilt, restore it with `.venv/bin/pip install -r requirements.txt`.

**The Google Calendar MCP is named `claude_ai_Google_Calendar`, not `google-calendar`.** The
`ALLOWED_TOOLS` default hardcoded in `plaud_watcher.py:46` is stale and would silently disable all
calendar writes. `.env` overrides it correctly — if calendar events stop appearing, check that
`ALLOWED_TOOLS` in `.env` still lists `mcp__claude_ai_Google_Calendar__*`.

**The prompt file is read once at startup** (`main()` reads it before the loop). Editing
`plaud-sync-prompt.txt` has no effect until the service restarts.

**Neither the email nor the Plaud MCP returns a link, but the recording `id` reconstructs one.**
`plaud_link` is `null` on every run because Plaud's emails carry no link, and the MCP has none either:
`presigned_url` is null and the only `data_link`s are S3 URLs that expire in 5 minutes
(`X-Amz-Expires=300`). So lookup is always by TITLE + DATE (subject format
`[Plaud-AutoFlow] <recording title>`), and the durable join key is the recording **`id`** returned by
`list_files`/`get_file`. The Plaud web app addresses a recording as `https://web.plaud.ai/file/<id>`,
so the prompt writes that (clickable) URL into the Notion `Source Link` — taking the load off the
fragile title match.

**Failures are recorded, not retried.** `process_message` marks the UID processed and `\Seen`
regardless of outcome, deliberately, to avoid a reprocess loop. A failed run needs manual replay.

**Auth is inherited, not configured.** Headless `claude -p` uses the interactive login and
user-scope MCP OAuth tokens of user `robert`. That is why the unit pins `User=robert` and
`Environment=HOME=/home/robert`. Running the watcher as any other user silently fails at the Claude
invocation. Verify MCP health with `claude mcp list`.

**IMAP UIDs are per-folder and not globally stable.** If the mailbox's UIDVALIDITY ever changes,
`processed.json` becomes meaningless and old mail can reprocess.

**`get_file` returns the FULL transcript whether you want it or not** (`source_list`, data_type
`transaction`). A prompt instruction to "skip the transcript" saves zero input cost — the tokens
arrive in context regardless. Only the *output* side (copying it into the Notion page) is optional
cost, at roughly $0.15 per 10k transcript tokens on Sonnet. `get_note`/`get_transcript` are strict
subsets of `get_file` — one `get_file` call fetches everything; extra calls are pure waste.

**Plaud's mind map is NOT exposed by the MCP** — no mindmap entry appears in any recording's
`note_list` (only `auto_sum_note`). Earlier notes said "No mind map was generated" because Claude
genuinely never receives one. The prompt therefore *synthesizes* a Mermaid `mindmap` code block from
the summary headings + `outline` topics; Notion renders it as a diagram. Don't "fix" a missing mind
map by hunting for a Plaud API that provides it — it doesn't exist in the MCP.

## Notion target

Database **🎙️ Plaud Synced Notes** — `https://app.notion.com/p/61e12e128c7f473b94f22641d8a36260`
Data source: `collection://bbc6c9aa-a96b-4501-a41a-8bd1b5a75866`

Schema (the prompt must stay in sync with these exact option strings):

- `Name` (title), `Date` (date)
- `Area` — Personal · Academics · Work · Research
- `Type` — **Meeting** · Reminder · Goal · Research · Dev · Client · Lecture · Coursework · Personal
  (Meeting detection is a first-class job: this DB replaces Notion's AI Meeting Notes)
- `Project` — FAMAIL · LARK · Construction Diagram/Doc AI · Car Sounds · Caltrans · Evidential Deep Learning · Unknown
- `Tags` (multi) — Meeting · Idea · Task · Follow-up · Personal
- `Source Link` (url) — set by the prompt to `https://web.plaud.ai/file/<recording id>` (clickable join key).
- `Routing` (select) — Pending · Done · Skip. **Machine-owned** hand-off flag for the distribution
  step: the sync run sets Pending (real project) or Skip (Unknown); only the distributor sets Done.
- `Synced` (created_time, auto), `Reviewed` (checkbox, left for the human)

## Cost, and the streamlining goal

Runs average **~$0.59 and ~65s** on Sonnet (n=3, pre-optimization). Reducing this is active work.
Levers:

1. ✅ *Applied.* The prompt no longer searches for the Notion database — Step 2 writes straight to
   `collection://bbc6c9aa-a96b-4501-a41a-8bd1b5a75866`.
2. ✅ *Applied.* Step 1 now calls `list_files` with `query` (title words) **and** `date_from`/
   `date_to` (email date) together, targeting a single-result lookup instead of listing + scanning.
3. ✅ *Resolved (deliberately).* The transcript is now INCLUDED in the Notion page by design. This
   was cheaper than it looked: `get_file` returns the transcript unconditionally (input cost was
   always being paid), so inclusion only adds output tokens. The old "skip the transcript" line
   also contradicted the calendar step, which scans the transcript.

The n=3 / ~$0.59 baseline predates all three levers — compare new runs in `runs.jsonl` (`cost_usd`,
`duration_ms`) against it to quantify the net effect (levers 1–2 push cost down, lever 3 up).
