# Planner — design spec

Status (2026-09-03, late): **LIVE — steps 1–4 built and running, plus the self-maintenance layer (§15)** — Notion structure (§4), sync-prompt extraction and voice commands (§5), `planner.py` + prompts + units (§6), email command channel (§15). Timers enabled (06:30 / 16:00), watcher restarted with the command channel, first run succeeded (§11). Steps 5–6 pending.
Companion to `CLAUDE.md`; operational facts move there as each step lands.

## 1. Goal

A Claude-powered planner that keeps one authoritative list of everything Robert has to do,
feeds it automatically from every place tasks originate, ranks it every morning and evening,
and puts the result where it will actually be seen: a Notion "Today" page, an email brief,
and (for dated items) Google Calendar. Redundancy is deliberate — the user wants deadlines
visible in more than one place.

Decisions made 2026-09-03:

| Question | Decision |
|---|---|
| System of record | One new unified Notion **Tasks** database under a new top-level **📋 Planner** page |
| v1 UI | Notion **Today** page + email push (push must come from outside Notion; Notion's own notifications get ignored) |
| Action-item extraction | Added to `plaud-sync-prompt.txt` at sync time, not a separate sweep |
| Calendar | Keep creating calendar events for deadline-type items; tasks and events coexist |
| Sources | Plaud, Canvas ICS feed, Google Calendar, SDSU email auto-forwarded from `rashe7414@sdsu.edu` (configurable allow/deny). No GitHub. |
| Priority | Dynamic/fuzzy, context-driven; manual priority is a prior that can be overridden with a reason |
| Project weights | High: BDA M.S. (thesis), DiCE Lab, Caltrans, GEOG 582, COMPE 510, BDA 696, SCIBER-CT, Evidential Deep Learning, Personal · Medium: Car Sounds, LARK, Unknown · Low: FAMAIL, Construction Diagram/Doc AI |
| Schedule | Morning run 06:30, evening run 16:00, plus on demand |
| Notifications | Email to `NOTIFY_EMAIL` with a `+planner` plus-address tag so it can be filtered |
| Old task DBs | Academic Assignments & Tasks, FAMAIL Research Tasks, famail_temporal Roadmap, LARK Todo: one-time triage into Tasks, then retire (LARK Todo is not shared; deleting it is fine) |

## 2. Principles (inherited from plaud-sync)

1. **The prompt is the program.** `planner-prompt.txt` holds every judgment: scoring, dedup,
   what goes on the Today page, how the email reads. `planner.py` is plumbing.
2. **Python gathers, Claude decides and writes.** Python fetches Canvas and email and hands
   Claude a compact text bundle. Claude is the only thing that writes to Notion or Calendar.
3. **Idempotent by key.** Every task carries a `Source Key`; every writer does
   create-or-update on it. Re-running is always safe.
4. **Never re-read note bodies.** Lecture transcripts already push single sync runs to $2–6.
   The planner reads task *properties* and small text bundles only.
5. **Linked views, not copies.** Project dashboards show tasks through filtered linked views
   of the one Tasks DB, exactly like the Plaud notes DB. No routing/distribution automation.

## 3. Architecture

```
 Plaud recording ──▶ plaud_watcher.py ──▶ claude -p (sync prompt)
                                             ├─ Notion: Plaud Synced Notes page   (existing)
                                             ├─ Calendar: dated events            (existing)
                                             └─ Notion: Tasks rows  ◀── NEW Step 3b

 Canvas ICS feed ─┐
 Forwarded email ─┤──▶ planner.py --mode morning|evening|now
 Google Calendar ─┤        │  (Python: fetch, filter, bundle, state)
 Tasks DB ────────┘        ▼
                     claude -p (planner prompt)
                        ├─ Notion Tasks: upsert from Canvas/email/calendar, dedup, score, prioritize
                        ├─ Notion "Today" page: body replaced each run
                        └─ JSON report → planner.py emails the brief to NOTIFY_EMAIL+planner
                                          and appends planner-runs.jsonl
```

Same repo, sibling of `weekly_digest.py`: shared `.env`, shared `.venv`, same systemd
pattern, same run-log conventions. The only coupling to the watcher is the Tasks DB schema
and one added step in the sync prompt.

## 4. Notion: what was built (2026-09-03)

| Object | URL / ID |
|---|---|
| **📋 Planner** page (top-level, private) | `https://app.notion.com/p/3d1eb3065110819fa358d3af8a3158b8` |
| **Tasks** database | `https://app.notion.com/p/b1c52e69d3924aea8962bee32440ffbe` |
| Tasks **data source** (what the prompts write to) | `collection://be0b1624-4ea6-43dd-acc2-3a828a8ab07e` |
| **☀️ Today** page (body replaced each run) | `https://app.notion.com/p/3d1eb30651108180942dff91930bdd10` |

The Planner page holds a callout, the Tasks database, the Today page, and an inline linked
view "Today's tasks". The Tasks database has views **Today**, **Upcoming**, **By project**
(board), **Waiting**, **Inbox**, **Done**, **Calendar** (by Due), and **Open** (every row not
Done/Dropped — the view the prompts READ through, see below).

**Notion SQL is metered on this workspace.** On 2026-09-03 `notion-query-data-sources` in SQL
mode hit "usage limit for Query Data Source" after ~15 queries in a session, while view mode
(`{"mode":"view","view_url":...}`) kept working and is documented as quota-free on every plan.
Both prompts therefore read through views and use SQL only as a fallback:

| View | `view_url` |
|---|---|
| Open (all not Done/Dropped; shows Name, Project, Status, Due, Hard deadline, Source Key, Mentions, Source, Priority, Score) | `https://www.notion.so/b1c52e69d3924aea8962bee32440ffbe?v=3d1eb306511081a5a601000c7530ed1a` |
| Done (Done/Dropped, newest first) | `https://www.notion.so/b1c52e69d3924aea8962bee32440ffbe?v=3d1eb30651108120a718000c760c0de9` |

View mode returns up to 100 rows per page with every property; Claude filters in context.
If the open-task count ever nears 100, the planner must page with `start_cursor`.

Creating the `Notes` relation as two-way added a **`Tasks`** relation property to the Plaud
Synced Notes DB, so every recording page lists the tasks extracted from it.

Property names and option strings are exact — both prompts depend on them.

| Property | Type | Values / notes |
|---|---|---|
| `Name` | title | Imperative, ≤ 80 chars: "Submit GEOG 582 Assignment 02" |
| `Status` | select | **Inbox** (needs a decision) · **Next** (actionable) · **In progress** · **Waiting** (blocked on someone) · **Done** · **Dropped** (merged or abandoned). A select, not a Notion status type: the API cannot define status options, so the planner would have depended on a manual UI step. |
| `Priority` | select | **P0**, **P1**, **P2**, **P3** — Claude-managed, rewritten every planner run |
| `Manual Priority` | select | same options — user-set prior; Claude may deviate but must say why in `Why now` |
| `Score` | number | 0–100, Claude-computed (see §7) |
| `Why now` | text | One sentence justifying the rank; mentions any manual-priority override |
| `Due` | date | Date, with time when the source gives one |
| `Hard deadline` | checkbox | True for submissions, registrations, cutoffs; false for targets/intentions |
| `Area` | select | Personal · Academics · Work · Research (same as Plaud DB) |
| `Project` | select | The 14 Plaud DB options: FAMAIL · LARK · Construction Diagram/Doc AI · Car Sounds · Caltrans · Evidential Deep Learning · DiCE Lab · SCIBER-CT · BDA M.S. · GEOG 582 · COMPE 510 · BDA 696 · Personal · Unknown |
| `Effort` | select | **XS** (≤15 min) · **S** (≤1 h) · **M** (half day) · **L** (multi-day) |
| `Source` | select | **Plaud** · **Canvas** · **Calendar** · **Email** · **Manual** |
| `Source Key` | text | Dedup key: `plaud:<file id>:<n>` · `canvas:<UID>` · `gcal:<event id>` · `email:<Message-ID>` · `manual` |
| `Source Link` | url | Plaud file URL, Canvas assignment URL, calendar htmlLink, or empty |
| `Notes` | relation → Plaud Synced Notes (two-way, synced as `Tasks`) | Every recording that mentioned this task (first = origin) |
| `Mentions` | number | Distinct sources that referenced this task; feeds the score |
| `Calendar Event` | url | htmlLink of the mirrored calendar event, if any |
| `Context` | text | 1–3 sentences from the source so the task is self-explanatory |
| `Waiting On` | text | Person/thing blocking a `Waiting` task |
| `Snoozed Until` | date | Planner hides the task from Today until this date, then clears it |
| `Completed` | date | Set by the planner when it first sees `Done` |
| `Created` / `Edited` | created_time / last_edited_time | automatic |

View filters cannot express "due within 7 days" (the view DSL has no relative dates), so
**Upcoming** is "open with a Due, sorted by Due" and the 7-day window lives on the Today page.
The Today view hides rows with any `Snoozed Until`; the planner clears that field once the
date passes, which keeps the filter honest.

Each project dashboard later gets a linked view filtered `Project = X` next to its Plaud view.

## 5. plaud-sync prompt: new Step 3b (draft text)

Inserted after Step 3 (page written) and before Step 4 (calendar). The sync run already has
the transcript in context and already resolves relative dates, so this costs only output
tokens plus one view-mode read of the Open view.

```
# Step 3b — Extract action items into the Tasks database
Data source: collection://be0b1624-4ea6-43dd-acc2-3a828a8ab07e   ("Tasks")

From the summary and transcript, list every concrete action item that Robert owns or that
has a deadline affecting him: things to submit, send, buy, decide, schedule, read, build,
reply to, register for, or follow up on. Skip vague intentions ("we should think about…"),
items clearly owned by someone else, and lecture content that is not an assignment.

First read the Tasks "Open" view ONCE in view mode (§4) and keep the rows whose Project
matches this note; SQL only if view mode errors; skip dedup rather than stall if both fail.
Then for each action item:
  - If an open row is clearly the same task (same deliverable, even if worded differently):
    UPDATE it — increment Mentions by 1, add this recording's page to Notes, and fill Due /
    Hard deadline / Context only if they were empty or this recording gives a more specific
    value. Do not create a duplicate.
  - Otherwise CREATE a row:
      Name           imperative, ≤ 80 chars, no trailing period
      Status         Next when the item is clearly actionable and owned by Robert; Inbox
                     when ownership or actionability is uncertain
      Due            absolute date (and time if stated), resolved against the RECORDING date
      Hard deadline  true for submissions, registrations, cutoffs, promised deliveries
      Area, Project  inherit from this note unless the item plainly belongs elsewhere,
                     using the same tie-breakers as Step 3
      Effort         XS / S / M / L best guess
      Source         Plaud
      Source Key     plaud:<recording id>:<n>   (n = 1, 2, 3… in this note)
      Source Link    https://web.plaud.ai/file/<recording id>
      Notes          relation to the page written in Step 3
      Mentions       1
      Context        1–3 sentences from the recording explaining the item
      Calendar Event leave empty here; if Step 4 creates an event for this item, set it then
Leave Priority, Score and Why now empty — the planner owns them.
If the recording is an UPDATE of an existing page (Step 2 found it), re-extraction must not
duplicate: match on Source Key prefix plaud:<id>: and update those rows instead.
```

Step 4 gains one line: when it creates a calendar event for an item that became a task, write
the event's htmlLink into that task's `Calendar Event`, and put the task's Notion URL in the
event description. The Step 5 report gains `"tasks": {"created": n, "updated": n}`.

## 6. The planner run

### 6.1 Files

| File | Role |
|---|---|
| `planner.py` | Gather sources, invoke Claude, send email, log. `--mode morning\|evening\|now`. |
| `planner-prompt.txt` | The program: reconcile, score, write Today page, compose brief. |
| `planner-sources.json` | Email allow/deny lists, Canvas course-code → Project map, windows, and `commands.senders`. Committed (no secrets). |
| `planner-commands-prompt.txt` | Applies emailed commands (done/defer/drop/add/…) to Tasks — run by the watcher, not the planner. Read per use, so edits need no restart. |
| `.claude/commands/plan-now.md` | `/plan-now [mode] [--dry-run]` runs the planner in the foreground. |
| `planner-state.json` | `last_run`, per-mode last run, seen email Message-IDs. Git-ignored. |
| `planner-runs.jsonl` | One record per run: mode, ok, cost, duration, counts from the report. |
| `planner@.service`, `planner@morning.timer`, `planner@evening.timer` | Template unit; `%i` becomes `--mode`. |

### 6.2 Python responsibilities

1. **Canvas (API, not the ICS feed).** `CANVAS_TOKEN` in `.env` (a personal access token from
   Canvas → Account → Settings; never committed). `GET /api/v1/planner/items` from `days_back`
   ago to `days_ahead` ahead, following `Link: rel="next"`, gives every assignment, quiz,
   discussion and event WITH submission state (`submissions.submitted/graded/missing/excused`)
   and Canvas's own "mark as done" (`planner_override.marked_complete`). Titles matching
   `skip_title_prefixes` are dropped; `context_name` (e.g. `GEOG582-01-Fall2026`) maps to a
   Project via `course_map`. Source Key = `canvas:<plannable_type>:<id>`. `GET /announcements`
   for the active courses (same window) is appended so deadline changes reach the planner.
   Without a token the run continues with "Canvas skipped". The ICS feed is no longer used.
   Observed 2026-09-03: `context_name` looks like `GEOG582-01:Introduction to GIS Programming`
   (the course map matches on the code substring); `html_url` is relative and gets the base
   prefixed; `submissions` is `false` for announcements and a dict otherwise; the token's owner
   is enrolled in 10 "courses" including homerooms, so `skip_context_patterns` drops the
   Arts & Letters, EOP and Student Tech homerooms from both items and announcements (the
   Graduate Students homeroom is kept — its announcements carry real deadlines).
2. **Email.** Connect read-only (`BODY.PEEK`) to the watcher's Gmail account, search INBOX
   `SINCE <lookback>` for mail not from plaud.ai, apply the allow list then the deny list
   from `planner-sources.json` — each pattern is a case-insensitive glob tested against
   BOTH the bare address and the full `Display Name <address>` header, so a sender can be
   denied by name when its address is shared (see §9). Skip Message-IDs already in state.
   Emit: message-id, from, date, subject, first ~1,500 chars of text.
3. **Bundle.** Concatenate: mode, today's date and weekday, timezone, Canvas list, email list,
   and a cap (~40k chars total; truncate email bodies first). Calendar and the Tasks DB are
   read by Claude via MCP, not by Python.
4. **Invoke** `claude -p "<prompt> + bundle" --model sonnet --allowedTools
   'mcp__notion__*,mcp__claude_ai_Google_Calendar__*' --output-format json`, timeout 900 s.
5. **Gate and send.** `ok` requires a parsed report with `today_page.url` and `email.body_html`
   (same positive-evidence rule as `_page_written`). Send the brief; on failure send a
   `[planner] FAILED` alert instead. Update state only on success.

### 6.3 Prompt outline (`planner-prompt.txt`)

```
Step 1  Read: the Tasks "Open" view in view mode (page with start_cursor if has_more), the
        "Done" view's first page (to set Completed on newly finished rows), and Google Calendar
        events from today to +14 days. No SQL unless view mode itself errors (§4 quota note).
Step 2  Ingest the bundle:
        - Canvas items → upsert by Source Key canvas:<uid> (Source=Canvas, Hard deadline=true,
          Project from the map, Effort by type: Quiz=S, Discussion=S, Assignment=M, Project=L).
        - Emails → create tasks only for concrete asks/deadlines addressed to Robert; Source
          Key email:<message-id>; Hard deadline when a date is stated as a due date.
        - Calendar events that are deadline-shaped (title contains due/deadline/submit/register,
          or an all-day event created from a Plaud note) → upsert by gcal:<id> unless a task
          with the same Calendar Event URL exists.
        - Dedup across sources: if two rows describe the same deliverable, keep the older,
          merge Due/Context/Notes, add Mentions, set the other to Dropped with Context
          "merged into <url>".
Step 3  Hygiene: set Completed on newly Done rows; clear Snoozed Until once passed; flag
        overdue; move Inbox rows older than 14 days into the brief's "decide or drop" list.
Step 4  Score every open, unsnoozed row per the policy (§7); write Score, Priority, Why now.
Step 5  Replace the body of the Today page (§8).
Step 6  Report JSON only (§6.4).
Evening mode differences: Step 2 runs the same; the brief leads with what was completed,
what rolls over, tomorrow's first hard deadline, and anything new since the morning.
```

### 6.4 Report shape

```json
{
  "mode": "morning",
  "ingested": {"canvas": 0, "email": 0, "calendar": 0},
  "tasks": {"created": 0, "updated": 0, "merged": 0, "completed": 0, "overdue": 0, "inbox": 0},
  "today_page": {"url": "https://app.notion.com/p/3d1eb30651108180942dff91930bdd10"},
  "email": {"subject": "[planner] Thu Sep 4 — 3 must · 2 hard deadlines this week",
            "body_html": "<inline-styled fragment>", "body_text": "plain fallback"}
}
```

## 7. Scoring policy (the fuzzy part, made legible)

Claude computes `Score` 0–100 from a skeleton it may bend by ±10 with a stated reason:

| Factor | Contribution |
|---|---|
| Deadline proximity | overdue hard deadline 100 · due today 90 · ≤2 days 80 · ≤7 days 60 · ≤14 days 40 · later 20 · none 15. Soft (non-hard) deadlines −15. |
| Project weight | **High +15**: BDA M.S. (thesis), DiCE Lab, Caltrans, GEOG 582, COMPE 510, BDA 696, SCIBER-CT, Evidential Deep Learning, Personal · **Medium +5**: Car Sounds, LARK, Unknown · **Low +0**: FAMAIL, Construction Diagram/Doc AI |
| Mentions | +5 per mention beyond the first, cap +15 |
| Owed to a person / blocking others | +10 (Context or Waiting On names someone expecting it) |
| Effort × proximity | XS/S due within 3 days +5 (quick win) · L due within 7 days +10 (start now) |
| Staleness | Inbox/Next with no Due and Created > 14 days ago +5 (surface to decide or drop) |
| Manual Priority | P0 floor 85 · P1 floor 65 · P3 cap 40. A hard deadline within 2 days may override; `Why now` must say so. |

Priority from Score: ≥80 **P0** · ≥60 **P1** · ≥35 **P2** · else **P3**.
Weights live in the prompt so they are edited like any other rule.

## 8. Today page and the email brief

Both render the same content; the page is the durable copy, the email is the push.

```
☀️ Today — Thursday, Sep 4                      (updated 06:30 · morning run · $0.41)
One-line verdict: "Plan A petition and scholarship both close today; nothing else is urgent."

MUST (≤3)     P0/P1 rows due today or overdue — Name · Project · Due · Effort · Why now
SHOULD (≤5)   next by Score
COULD         the rest of P2, collapsed
HARD DEADLINES — next 7 days   table: Date · Task · Project · Source
WAITING ON    Task · who · since
INBOX (n)     "decide or drop": stale or ambiguous items
DONE          since the last run (evening) / yesterday (morning)
```

Email: subject `[planner] <weekday Mon D> — <n> must · <m> hard deadlines this week`;
inline-styled HTML fragment ≤ 640 px like the digest; every task links to its Notion row.
Sent **From** the watcher account (`nthperson.dev@gmail.com`) **To** `NOTIFY_EMAIL` rewritten
as `local+planner@gmail.com` (the script inserts the tag; `.env` stays unchanged).
On the phone: mark `nthperson.dev@gmail.com` as a **VIP** in iOS Mail for VIP-only
notifications (Gmail's iOS app cannot notify per label). In Gmail: filter
`to:(local+planner@gmail.com)` → label **Planner**. Failure alerts use `+planner` too.

## 9. SDSU mail → the planner (decided: auto-forward)

The watcher's mailbox `nthperson.dev@gmail.com` receives only Plaud mail. SDSU and Canvas
mail arrives at **`rashe7414@sdsu.edu`**, so a Gmail filter there forwards the relevant mail
to the watcher account. Forwarded messages keep the original `From:` header, so the
planner's allow/deny lists apply as a second layer. One-time setup, in the SDSU account:

1. Gmail → ⚙ → **See all settings** → **Forwarding and POP/IMAP** → **Add a forwarding
   address** → `nthperson.dev@gmail.com`. Gmail emails a confirmation to that address;
   open it in the watcher account and click the confirm link (the watcher ignores it — not
   from plaud.ai). Leave **Disable forwarding** selected on that page: forwarding happens
   only through the filter below, not for all mail.
2. **Filters and Blocked Addresses** → **Create a new filter** → *From:*
   `(sdsu.edu OR instructure.com)` → **Create filter** → tick **Forward it to:**
   `nthperson.dev@gmail.com` → **Create filter**.
3. Done. Filters act on new mail only; nothing historical is forwarded.

If **Add a forwarding address** is missing, the SDSU Workspace admins block external
forwarding; fall back to a second IMAP login (`SCAN_IMAP_USER` / `SCAN_IMAP_PASSWORD`
in `.env`, app password) — `planner.py` should support both.

`planner-sources.json` (written 2026-09-03) — patterns are case-insensitive globs tested
against the bare address AND the full `Name <address>` header:

- **allow**: `*@sdsu.edu`, `*@*.sdsu.edu`, `*@instructure.com`, `*@*.instructure.com`
- **deny** (from Robert, 2026-09-03): SDSU Athletics via Ticketmaster, University Police,
  Student Health Services, Bookstore, Well-being & Health Promotion, Student Affairs and
  Campus Diversity, the President's office, the VP for Business & Financial Affairs,
  GradLife via Constant Contact, and **College of Arts & Letters Homeroom** — the last one is
  denied by *display name*, because its address `notifications@instructure.com` is the same
  one every Canvas course announcement uses.

## 10. Systemd

```
planner@.service      ExecStart=/home/robert/plaud-sync/.venv/bin/python /home/robert/plaud-sync/planner.py --mode %i
                      User=robert, EnvironmentFile=.env, HOME=/home/robert   (same as the digest)
planner@morning.timer OnCalendar=*-*-* 06:30   Persistent=true
planner@evening.timer OnCalendar=*-*-* 16:00   Persistent=true
```

On demand: `sudo systemctl start planner@now.service` from any laptop, or a `/plan-now`
skill that runs `planner.py --mode now` in the foreground. Phone-triggered runs are v2 (§13).

## 11. Cost and safety

- Expected **$0.30–0.80 per steady-state run** on Sonnet (properties + small bundles, no
  transcripts); two runs a day ≈ $20–50/month. Log `cost_usd` per run and revisit after a week.
  **First real run (2026-09-03 20:55, mode now): $2.14 / 519 s** — a one-time bulk: 27 Canvas
  items + 2 emails ingested, 32 tasks created, 7 closed from Canvas submission state, 26 open,
  2 overdue, Today page written, brief emailed. Steady-state runs should be far cheaper because
  the prompt skips rows whose Score/Priority/Why now are unchanged; if they are not, the levers
  are `PLANNER_MODEL=haiku` and narrowing `canvas.days_ahead`.
- `--allowedTools` limited to Notion and Calendar; keep every MCP **write** tool out of the
  `ask` list in `.claude/settings.json` (the 2026-07-22 stall applies here too).
- Success is gated on positive evidence (Today page URL + email body), never exit status.
- Idempotency by `Source Key` means a re-run after a partial failure updates instead of
  duplicating; the calendar step still needs its own near-duplicate search.
- Secrets: `CANVAS_ICS_URL` contains a bearer-like token and lives only in `.env`.

## 12. Build order

1. ✅ **Notion** (2026-09-03): Planner page, Tasks DB with the §4 schema and views, Today page,
   plus the `Task ID` unique-ID property (prefix `Task`, so codes read `Task-17`; Notion
   requires a ≥2-character prefix, and the prefix was changed from `TK` on 2026-09-03 without
   renumbering).
2. ✅ **Sync prompt Step 3b** + Step 4/5 tweaks (2026-09-03). Validated with the dev loop on the
   08-27 Caltrans PC procurement note: 1 task, every property as specified, linked to the
   existing calendar event, no duplicates; $1.29 / 127 s on the update path vs $0.57 for that
   note's original run. Service restart required for the live path to use it.
3. ✅ **planner.py + planner-prompt.txt + units + /plan-now** written 2026-09-03 (dry run OK:
   inbox scan and bundle work; the forwarded Canvas token notice was the first email through).
   Still to do by Robert, in this order:
   ```
   # 1. fix the token line in .env so it is ONE line: CANVAS_TOKEN=<token>   (then rotate the
   #    token in Canvas — the malformed line echoed it into a shell error once)
   # 2. load the new prompt + command channel into the watcher
   sudo systemctl restart plaud-sync
   # 3. install and start the planner timers
   sudo cp planner@.service planner@morning.timer planner@evening.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now planner@morning.timer planner@evening.timer
   systemctl list-timers 'planner@*'
   # 4. first real run (writes the Today page, emails the brief)
   sudo systemctl start planner@now.service     # or /plan-now in Claude Code
   ```
   ✅ All four done by Robert 2026-09-03 20:54–20:55 PDT (token fixed and rotated, watcher
   restarted with the command channel live, timers enabled for 06:30 / 16:00, first run
   started). Note: `planner@.service` is `Type=oneshot`, so `systemctl start` blocks until the
   run finishes (several minutes) — that is normal, not a hang; use `--no-block` to return early.
4. ✅ **Email source**: forwarding filter created by Robert 2026-09-03 (From `sdsu.edu OR
   instructure.com` → watcher account). Seed further deny entries from the first week's false
   positives.
5. **One-time triage** of the four stale DBs into Tasks; linked views on project dashboards.
6. Fold a weekly review (completed / slipped / upcoming) into the Sunday digest.

## 13. Later (not v1)

- **Artifact dashboard**: a private claude.ai page that reads/writes the same Tasks DB through
  the Notion connector and can re-rank on demand from the phone.
- **Phone-triggered run**: an email to the watcher account with subject `[plan]` picked up by
  the existing IDLE loop.
- **Canvas submission state** via the Canvas API (needs a token) so submitted items auto-close.
- Retire semester course Projects from the prompt at term end (keep the Notion options).

## 15. Self-maintenance (added 2026-09-03)

The list keeps itself current through three layers, cheapest first. Decisions: apply email
commands **immediately**; "defer" with no date hands the task to the **next morning brief**.

### 15.1 Signals that need nothing from Robert
- **Canvas submission state** (§6.2): a task whose Canvas item is submitted, graded, excused or
  marked complete is set Done with Completed = today by the next planner run. Canvas never
  reopens a Done row. `state=missing` is reported as overdue.
- **Plaud recordings** (`plaud-sync-prompt.txt` Step 3c): completion statements and instructions
  spoken in any recording are applied at sync time — done, defer to a date, defer with no date
  (Snoozed Until = next day, Due untouched), drop, waiting on <person>, priority, started,
  corrections — with calendar follow-through (a moved Due moves the linked event; events are
  never deleted). References are resolved by Task ID, project, person, recency and wording;
  ambiguous ones land in the report's `unresolved` list. Robert's intent: recordings such as
  "I just finished the assignment for my Python programming class, mark it complete" and "the
  task Reza gave me yesterday needs to be pushed to Thursday next week" manage the list.
- **Forwarded email** that answers a Waiting task flips it back to Next.

### 15.2 The email command channel
- Every brief is sent From the watcher account with Reply-To set, so a plain reply is a command.
  Each task line carries three mailto links (`✓ done · → defer · ✕ drop`) that open a prefilled
  mail to the watcher address with the command in the subject — two taps on the phone. Siri
  Shortcuts that email the same address work identically.
- `plaud_watcher.py` treats unseen mail FROM `commands.senders` (planner-sources.json) plus
  `NOTIFY_EMAIL` as a command when (a) the subject contains `[planner]` (a reply to a brief), or
  (b) the subject or first body line starts with a command verb — done, finished, complete, mark,
  defer, push, postpone, snooze, drop, remove, delete, cancel, start, reopen, waiting, priority,
  note, add, schedule, book, set up, create, new, move, reschedule, put — or with a task code, or
  (c) as a fallback, the mail is short (≤ 500 chars) and not a forward, since Robert rarely mails
  this inbox for any other reason. Quoted text and signatures are stripped. It runs
  `planner-commands-prompt.txt` headlessly (timeout `COMMAND_TIMEOUT`, default 300 s), logs a
  `kind: "command"` record to `planner-runs.jsonl`, and replies with a confirmation
  (`✓ applied / + created / 📅 calendar / ? unresolved`). Free text is allowed; ambiguity is
  reported, not guessed. Subject-only commands work: `Remove Task-5`, `Defer Task 20`,
  `Add an appointment with Reza to my schedule for next Thursday at 12pm over Zoom`.
- Task references: `Task-17`, `Task 17`, `task17`, `#17`, bare `17`, or a description resolved by
  project/person/recency/wording. Meanings (phrasing is free): done/finished/complete ·
  defer/push/postpone [to when] · snooze [until when] · drop/remove/delete/cancel · start ·
  reopen · waiting on <who> · priority P0–P3/urgent/low · note <text> · add <text> [by <date>]
  [(<project>)]. Relative dates resolve against the email's date; a weekday name means the coming
  one, "next <weekday>" the one in the following calendar week; every confirmation states the
  resolved date so a misread can be corrected with a follow-up command.
- **Calendar commands** (added 2026-09-03): `add/schedule/book/set up <what> [with <who>] <when>
  [at <time>] [over Zoom | at <place>]` creates an event (1 h default, all-day when untimed,
  "Zoom — link to be added" when no link, no attendees unless an address is given; meetings are
  never tasks); `move/reschedule <event> to <when>` updates the single matching event;
  `cancel/remove/delete <event>` deletes it under the **evidence rule**. Dropping a task by explicit
  command also deletes its linked event under the same rule.
- **Evidence rule for deletions** (Robert's policy: remove on good evidence, never on a hunch):
  a task's linked event only when THAT task is explicitly dropped and the event is the one in its
  `Calendar Event`; a named event only when exactly one event matches both title words and
  date/window; never an event with other attendees unless the command explicitly cancels the
  meeting with them; never on similarity alone. The same rule governs voice instructions in
  `plaud-sync-prompt.txt` Step 3c. The autonomous planner run still never deletes anything.
- Non-command mail from those senders is ignored and left unread; the planner's email scan
  skips command senders entirely, so nothing is double-processed.

### 15.3 What the briefs now do
- **Evening brief = check-in**: "Done today", then "still open from today's Must/Should — did you
  finish these?" with codes and links, tomorrow's first hard deadline, anything new since morning.
- Both briefs list **"Applied since the last run"** from the command log, which is the audit
  trail for voice and email commands.

### 15.4 Cost
Command runs read one view and make a few page updates. Measured 2026-09-03: `add … by friday
(Personal)` cost **$0.78 / 58 s** on Sonnet (the view read dominates). Planner runs are unchanged
(§11). If the command channel gets chatty, batching into the next run is a one-line change in the
watcher, and `PLANNER_MODEL=haiku` for commands is the other lever.
