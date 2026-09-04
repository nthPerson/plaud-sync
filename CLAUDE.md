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
always the wrong move. Since 2026-09-03 the prompt also writes action items to the planner's
Tasks DB (see the Planner section). Note that the prompt is read once at startup, so a prompt edit still requires
a service restart.

## Runtime layout

| Path | Role |
|---|---|
| `plaud_watcher.py` | IMAP IDLE loop + `claude -p` invoker. ~235 lines, no deps beyond `imapclient`. |
| `plaud-sync-prompt.txt` | The actual task definition handed to headless Claude. |
| `.env` | All config. Loaded by systemd via `EnvironmentFile=`. Contains a Gmail **app password**. |
| `plaud-sync.service` | Repo copy of the unit. **Drifted from the installed one — see gotchas.** |
| `processed.json` | Set of handled IMAP UIDs. Idempotency guard. |
| `runs.jsonl` | One JSON record per Claude run: `ok`, `attempt` (1 or 2), `cost_usd`, `duration_ms`, `report` (parsed JSON report; `summary` holds raw text only when parsing fails). |
| `weekly_digest.py` + `weekly-digest-prompt.txt` | Sunday-evening digest: headless Claude queries the Notion DB and composes an HTML email (tables, inline styles only) with a plain-text fallback; script sends it to `NOTIFY_EMAIL`. |
| `plaud-digest.service` / `plaud-digest.timer` | Systemd units for the digest (installed copies live in `/etc/systemd/system/`). |
| `planner.py`, `planner-prompt.txt`, `planner-commands-prompt.txt`, `planner-sources.json`, `planner@.service` + timers | The planner (see the Planner section). `planner-runs.jsonl` / `planner-state.json` are its git-ignored runtime files. |
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

# weekly digest (Sunday 17:00 via plaud-digest.timer; emails NOTIFY_EMAIL)
systemctl list-timers plaud-digest.timer
sudo systemctl start plaud-digest.service      # fire one digest right now (sends real email)
set -a; source .env; set +a; .venv/bin/python weekly_digest.py   # same, foreground
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

**Failures get exactly ONE automatic retry, then an email alert.** After a failed run,
`process_message` waits `RETRY_DELAY` (default 120s) and re-runs once — safe because the prompt's
Step 2 makes runs idempotent (create-or-update keyed on Source Link). If the retry also fails, a
failure alert is emailed to `NOTIFY_EMAIL` via the same Gmail account (SMTP + app password), and the
UID is still marked processed/`\Seen` to avoid a reprocess loop. Beyond that one retry, a failed run
needs manual replay (`/replay-note`).

**MCP *write* tools in `.claude/settings.json`'s `ask` list silently break the headless watcher.**
`ask` outranks the `--allowedTools` allow the watcher passes, and headless `claude -p` has no one to
approve the prompt — so the call stalls, Claude gives up with a prose apology, and nothing is written.
This blocked `notion-create-pages` on 2026-07-22 even though the identical config had written fine two
days earlier: a Claude Code precedence change started letting the project `ask` rule win over the CLI
allowlist. Keep the Notion/Calendar **write** tools OUT of `ask` — the service depends on
`--allowedTools mcp__notion__*,mcp__claude_ai_Google_Calendar__*` with no `ask` override (the `ask`
list is now just the `sudo systemctl` entries, which only ever run interactively). And because a
stalled run still exits 0 with `is_error=false`, `log_run` no longer trusts exit status alone: `ok` is
gated on `_page_written(report, summary)` — positive evidence (a `notion_page` URL in the report, or a
Notion link in the final text) that a page actually landed. Before that fix the 07-22 stall logged
`ok=True`, so it never retried or alerted. A false negative there is harmless: the prompt's
create-or-update idempotency means the retry updates the page instead of duplicating it.

**Notion SQL queries are metered on this workspace plan.** `notion-query-data-sources` in SQL
mode returned "Your workspace has reached the usage limit for Query Data Source" on 2026-09-03
after roughly fifteen queries in one session. The sync's Step 2 (existing-page check) and Step
3b (task dedup) both query, and the planner will query several times per run, so the budget is
shared. The tool documents **view mode** (`mode: "view"` with a `view_url`) as quota-free on
every plan, so prompts should read through pre-built views — the Tasks DB has an **Open** view
for exactly this — and treat SQL as the fallback, never the default. Fetches, searches, and
page writes are not metered.

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

**Adding a project takes TWO edits — the prompt AND the Notion select.** Listing a new `Project` value
in `plaud-sync-prompt.txt` does not create it in Notion; the option must also exist on the `Project`
property of `collection://bbc6c9aa-a96b-4501-a41a-8bd1b5a75866`, or the automation writes a value the
schema doesn't have. `DiCE Lab` sat in the prompt with no matching Notion option until 2026-08-19. Add
options with `notion-update-data-source` — note that `ALTER COLUMN "Project" SET SELECT(...)` REPLACES
the whole option list, so re-list every existing option (with its color) plus the new one, then re-fetch
to confirm nothing was dropped. Give the new project a dashboard too (linked view filtered
`Project = X`), or its notes surface nowhere.

## Notion target

Database **🎙️ Plaud Synced Notes** — `https://app.notion.com/p/61e12e128c7f473b94f22641d8a36260`
Data source: `collection://bbc6c9aa-a96b-4501-a41a-8bd1b5a75866`

Schema (the prompt must stay in sync with these exact option strings):

- `Name` (title), `Date` (date)
- `Area` — Personal · Academics · Work · Research
- `Type` — **Meeting** · Reminder · Goal · Research · Dev · Client · Lecture · Coursework · Personal
  (Meeting detection is a first-class job: this DB replaces Notion's AI Meeting Notes)
- `Project` — FAMAIL · LARK · Construction Diagram/Doc AI · Car Sounds · Caltrans · Evidential Deep
  Learning · DiCE Lab · SCIBER-CT · BDA M.S. · GEOG 582 · COMPE 510 · BDA 696 · Personal · Unknown ·
  **Planner** (added 2026-09-04: command recordings whose purpose is managing the task list or
  calendar; they surface on the 📋 Planner page, not on a project dashboard — see the Planner section)
- `Tags` (multi) — Meeting · Idea · Task · Follow-up · Personal
- `Source Link` (url) — set by the prompt to `https://web.plaud.ai/file/<recording id>` (clickable join key).
- `Meeting Date` (date) — set to the recording's start date+time ONLY when Type = Meeting; the
  project dashboards use it as their meeting timeline column.
- `Synced` (created_time, auto). A `Reviewed` checkbox once existed but was removed — the user
  decided a review workflow was maintenance they'd never keep up with; don't reintroduce one.
- `Tasks` (relation, auto-added 2026-09-03) — the synced side of the planner's `Notes` relation;
  lists the tasks extracted from that recording. Nothing in the sync prompt sets it directly.

Project dashboards consume this DB via **linked database views** (filtered `Project = X`, with a
`Type = Meeting` tab) — there is deliberately NO distribution automation copying notes elsewhere,
and a `Routing` property that once existed for that purpose was removed. Don't reintroduce either.

**`Personal` and `Unknown` are not the same fallback.** `Personal` is a real project for personal-life
notes (memos, health, goals, budgeting, travel) and feeds the *Personal Dashboard*. `Unknown` is only
for a work/academic/research note with no identifiable project, and feeds *📥 Unfiled Notes*
(`https://app.notion.com/p/3c2eb3065110815dbceffcf1729a0ab8`). The prompt enforces this: `Area = Personal`
⇒ `Project = Personal`, never `Unknown`. Merging the two was considered and rejected — it would have
dumped ambiguous work/school notes onto the Personal Dashboard.

**Fall 2026 courses are Projects named by course code** — GEOG 582 (Intro to GIS Programming, Nara),
COMPE 510 (Machine Learning for Engineers, Xie), BDA 696 (Process & Model Big Data, Lafler) — each with
a course dashboard page in the Courses DB carrying a `Project = <code>`-filtered Plaud view plus
relation-filtered Assignments/Lectures/Class Notes/Group Project views. COMPE 510 doubles as the
SCIBER-CT ARX course: course CONTENT files to `COMPE 510`; only traineeship-level matters file to
`SCIBER-CT` (the prompt's tie-breakers encode this). When a semester ends, the course options can be
retired from the prompt but must stay in the Notion select or old rows lose their value.

**`BDA M.S.` is the degree, not its courses.** It catches only M.S. degree ADMINISTRATION — program
of study, adviser meetings, advancement to candidacy, BDA 600/799A (Plan A thesis) logistics,
graduation. Course content files to the course's project even when the course satisfies an M.S.
requirement (GEOG 582 is the M.S. Python core), and thesis RESEARCH content files to its research
project (e.g. FAMAIL) — the prompt's tie-breakers encode both. Dashboard: *Big Data Analytics M.S.*
(`3c2eb3065110800bbc45c7e14e2d0eb6`), with the degree-progress tracker and a `Project = BDA M.S.`
Plaud view.

**`SCIBER-CT` vs `DiCE Lab` are distinct** and both trace to Dr. Akhavian, so his presence in a note
decides nothing. SCIBER-CT is the NSF NRT traineeship (certificate coursework, cohort, stipend/RCR,
internship, hackathon, symposium); DiCE Lab is the research lab's own work. Dashboards:
*SCIBER-CT Dashboard* (`3c2eb3065110808aacaac47ceac0a82b`), *DiCE Lab* (`257eb306511080fdaeded25422df0518`).

## Planner (task/deadline automation)

A sibling automation designed and built 2026-09-03; the full design is `PLANNER-SPEC.md` (read
it before touching anything planner-related). Same principles as the watcher: Python gathers,
Claude decides and writes, the prompt is the program.

| Path | Role |
|---|---|
| `planner.py` | `--mode morning\|evening\|now [--dry-run] [--no-email]`. Gathers Canvas (API) + forwarded email + recent commands into a text bundle, runs `claude -p` with `planner-prompt.txt`, emails the brief to `NOTIFY_EMAIL` with a `+planner` tag, logs to `planner-runs.jsonl`, keeps `planner-state.json`. |
| `planner-prompt.txt` | The planner program: ingest/upsert by `Source Key`, dedup, hygiene, scoring policy (project weights live here), Today page layout, email brief. |
| `planner-commands-prompt.txt` | Applies emailed commands (`done TK-17`, `defer TK-19 mon`, `add … by …`, free text) to Tasks. Run by **the watcher**, read per use (no restart needed to edit it). |
| `planner-sources.json` | Email allow/deny globs (matched against display name AND address), Canvas course map, `commands.senders`. |
| `planner@.service`, `planner@morning.timer` (06:30), `planner@evening.timer` (16:00) | Template unit: `%i` is the mode. Install with `sudo cp … /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now planner@morning.timer planner@evening.timer`. |
| `/plan-now [mode] [--dry-run]` | Foreground run from Claude Code. |

Notion objects:
- **📋 Planner** page `https://app.notion.com/p/3d1eb3065110819fa358d3af8a3158b8` (top-level)
- **Tasks** DB `https://app.notion.com/p/b1c52e69d3924aea8962bee32440ffbe`, data source
  `collection://be0b1624-4ea6-43dd-acc2-3a828a8ab07e` — Status is a *select* (Inbox · Next ·
  In progress · Waiting · Done · Dropped) because the API cannot define status-type options.
  `Source Key` is the idempotency key; `Task ID` is a unique ID (`Task-<n>`, the code Robert types
  in replies — prefix changed from `TK` on 2026-09-03 without renumbering); `Priority`/`Score`/
  `Why now` are planner-owned; `Manual Priority` is Robert's prior.
- **Open** view (read path for every prompt — SQL is metered, view mode is not):
  `https://www.notion.so/b1c52e69d3924aea8962bee32440ffbe?v=3d1eb306511081a5a601000c7530ed1a`
- **☀️ Today** page `https://app.notion.com/p/3d1eb30651108180942dff91930bdd10` — body replaced
  by every planner run.
- **Command Log** DB `https://app.notion.com/p/08ac20a559d646c89b36d922da7c58c1`, data source
  `collection://f91d236c-b7d9-4abe-82ca-f0ab28f5288b` (added 2026-09-04) — one row per voice
  command, email command and planner run, written by Claude at the end of each run (Channel:
  Voice · Email reply · Email subject · Email free text · Planner run; Result: Applied · Partial ·
  Nothing; relations to the tasks touched and, for voice, the recording). Views: All · Voice ·
  Email · Planner runs · Needs attention. Failed runs never reach it — those live only in
  `planner-runs.jsonl` and the failure email.
- The **📋 Planner page layout** (2026-09-04): callout → Today → Tasks (inline, every view) →
  Command Log (inline) → "Command recordings" (linked view of Plaud notes, `Project = Planner`).
  Both databases are *inline* so all their views show on the page — keep it that way.

**Command recordings are `Project = Planner`.** When a recording's primary purpose is managing the
list ("if you're an agent managing my task list…", "mark X done", "push Y to Thursday"), the sync
prompt files it under `Planner`, runs Step 3c BEFORE writing the page so the changes land ~2 min
sooner, and writes a light page (Summary + Transcript, no mind map). Mixed recordings keep their
real project. Tasks never carry `Planner` as a Project — the option exists only on the Plaud DB.

**The watcher now has a second job.** Besides Plaud mail, `plaud_watcher.py` treats unseen mail
FROM Robert's own addresses (`commands.senders` + `NOTIFY_EMAIL`) as planner commands when the
subject contains `[planner]`, when the subject/first line starts with a command verb or a task
code (done, finished, complete, mark, defer, push, postpone, snooze, drop, remove, delete, cancel,
start, reopen, waiting, priority, note, add, schedule, book, set up, create, new, move,
reschedule, put, `Task-5`), or — fallback — when the mail is short (≤ 500 chars) and not a
forward. It applies them immediately via `planner-commands-prompt.txt` (read per use, so prompt
edits need no restart; regex edits do) and replies with a confirmation. Commands cover tasks AND
the calendar: "Add an appointment with Reza … next Thursday at 12pm over Zoom" creates an event,
"move … to …" updates one, "cancel/remove/delete …" deletes one.

**Calendar deletion is allowed only under the evidence rule** (Robert's policy, 2026-09-03: remove
on good evidence, never on a hunch). A task's linked event may be deleted only when that task is
explicitly dropped by email or voice; a named event only when exactly one event matches both
title words and date; never an event with other attendees unless the command explicitly cancels
the meeting with them. The autonomous planner run (`planner-prompt.txt`) still never deletes.

**`plaud-sync-prompt.txt` Steps 3b/3c write and manage Tasks** (added 2026-09-03): 3b extracts
Robert's action items into the Tasks DB (keyed `plaud:<recording id>:<n>`, dedup against the Open
view, `Mentions` bumped instead of duplicating; Step 4 cross-links calendar events into
`Calendar Event`). 3c applies task instructions spoken in the recording — "mark the Python
assignment complete", "push Reza's task to next Thursday" — including moving the linked calendar
event. Validated with the dev loop on the 08-27 Caltrans PC procurement note: 1 row, all
properties correct, no duplicate events, $1.29 / 127 s on the update path (that note's original
run cost $0.57; budget roughly +$0.3–0.7 per recording). The report carries
`"tasks"`, `"task_updates"` and `"unresolved"`.

**Canvas is read through its API, not the ICS feed.** `CANVAS_TOKEN` (personal access token,
`.env` only) unlocks `/api/v1/planner/items`, which carries submission state — the planner
closes a task automatically once Canvas shows it submitted, graded, excused or marked complete.
Without the token the run proceeds with "Canvas skipped". `CANVAS_BASE_URL` defaults to
`https://sdsu.instructure.com`. `planner-sources.json` → `canvas.skip_context_patterns` drops
homeroom "courses" (Arts & Letters, EOP, Student Tech) from items and announcements.

**`systemctl start planner@<mode>.service` blocks until the run ends** (`Type=oneshot`, several
minutes). That is not a hang; add `--no-block` or use the timers.

**Planner cost baseline.** First run 2026-09-03: **$2.14 / 519 s** — bulk creation of 32 tasks from
27 Canvas items and the calendar, 7 auto-closed from Canvas submission state. Steady-state runs
should be well under $1; compare `cost_usd` in `planner-runs.jsonl` (`kind: "plan"`) against
this. Command runs (`kind: "command"`) measured $0.41–0.78. Levers if it drifts: `PLANNER_MODEL=haiku`,
smaller `canvas.days_ahead`, batching commands into the next run.

**Email into the planner comes by forwarding.** SDSU/Canvas mail is auto-forwarded from
`rashe7414@sdsu.edu` to the watcher account by a Gmail filter (`from:(sdsu.edu OR
instructure.com)`); original `From:` headers survive, so `planner-sources.json` allow/deny still
applies. The planner reads the inbox read-only (`BODY.PEEK`) and tracks seen Message-IDs in
`planner-state.json`; it never marks mail seen. The watcher is the only thing that marks mail
seen (Plaud mail and command mail).

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
