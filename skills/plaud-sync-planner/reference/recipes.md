# Recipes

Standard operations. Each names the cheapest read that answers it. Schema and write formats are in
`tasks.md`; the evidence rule is in `calendar.md`.

---

## Query

### R1 — What's on my plate
Fetch the **☀️ Today page** (`3d1eb30651108180942dff91930bdd10`). The planner wrote it at 06:30 or
16:00 with Must / Should / Could already ranked; one fetch answers the question.

Re-derive from the **Today view** only if the page is stale (no run since the relevant change) or
the question needs a cut the page does not show. Never rewrite the page yourself.

### R2 — What's overdue or slipping
**Upcoming view**, take rows with `Due` before today that are not Done/Dropped. For each, report
the code, name, how many days late, and `Why now`. Rows overdue for **several days in a row** are
the signal worth naming explicitly — that pattern is the system's known failure mode, and the
useful next question is "close, defer, or drop?", not "here it is again".

### R3 — This week
Two reads: **Upcoming view** for hard deadlines in the next 7 days, and `list_events` for the
calendar. Then cross-check: **hard deadlines whose task has an empty `Calendar Event`** are
invisible on the calendar and worth flagging.

### R4 — Project pulse
**By project view** (board, grouped) for open tasks, plus a Notes DB query filtered `Project = X`
sorted by `Date` desc for recent recordings. Report open work, what is overdue, and what the last
recording said about it.

### R5 — Recall: "what did we decide about X"
Search the **Notes DB** — `notion-ai-search` or a `rows` query on title/Project — then fetch the
page. The transcript is in the body. Do **not** call Plaud's `get_file` (see `plaud.md`).

### R6 — Trace a task to its source
Read the row's `Source Key` and `Source Link`. Decode per `tasks.md` — `plaud:<id>:<n>` →
`https://web.plaud.ai/file/<id>`, and the `Notes` relation points at the note page. Remember the
backslash escaping in `rows` mode.

---

## Modify

### R7 — Change a task's state
Semantics are **identical to the email and voice channels** — same words, same effects:

| Asked | Do |
|---|---|
| done / finished / complete / submitted | `Status` = Done, `Completed` = today |
| defer / push / postpone **to `<date>`** | `Due` = that date, keep `Hard deadline`, clear `Snoozed Until` |
| defer / later / not now, **no date** | `Snoozed Until` = tomorrow; **leave `Due` alone** — the next brief decides |
| snooze until `<date>` | `Snoozed Until` = that date; `Due` unchanged |
| drop / remove / cancel | `Status` = Dropped; append "Dropped by Claude session `<date>`" to `Context`; then the event, under the evidence rule |
| start / working on | `Status` = In progress |
| waiting on `<who>` | `Status` = Waiting, `Waiting On` = who |
| urgent / top priority / can wait / low | `Manual Priority` = P0 / P1 / P2 / P3 |
| note `<text>` | append to `Context` |
| correction ("it's actually due Friday") | update that field |

After any `Due` or `Status` change, set an interim `Why now`. Leave `Priority` and `Score` alone.

Resolve a reference by `Task-<n>` first, then by project + person + recency + wording. **If two
rows fit equally well, change neither** and say which two.

### R8 — Add a task
Per the template in `tasks.md`. `Source` = Manual, `Source Key` = `manual:<YYYY-MM-DD>:<n>`. Do not
invent a `Due` that was not stated. Re-read the row afterwards to report its `Task-<n>` code.

Check the **Open view** first — capture happens from four channels, so it may already exist. If it
does, bump `Mentions` instead of creating a duplicate.

### R9 — Schedule, move, or cancel an event
`calendar.md`. Confirm before acting; state the resolved date. A meeting is never also a task.

### R10 — Fix a misfiled note
Update `Project`/`Area` on the note page **and** on the tasks it produced (its `Tasks` relation).
Half-fixing it leaves the note on one dashboard and its work on another.

---

## Maintain

### R11 — Merge duplicates
Keep the **older** row. Merge into it the better `Due`, `Context` and `Source Link`; set `Mentions`
to the sum; union the `Notes` relations. Set the newer row to `Dropped` with
`Context` = "merged into Task-`<n>`". Prefer the **Canvas** row as survivor for coursework —
Canvas closes it automatically when submitted.

### R12 — Weekly review
`grooming.md`.

### R13 — Integrity sweep
`grooming.md`.

### R14 — Log the session
One Command Log row, `Channel` = `Claude session`, per the template in `tasks.md`. Do this once at
the end of a session that changed anything — not per edit.

### R15 — Reconcile Plaud against Notion
1. `list_files` over a window (default: the last 14 days).
2. Read the Notes DB for the same window; collect `Source Link` values.
3. Report recordings whose `https://web.plaud.ai/file/<id>` appears in no note page.

Each gap is a recording the automation consumed without filing. Report it with its title, date and
id — **do not file it by hand** (`plaud.md`); it needs `/replay-note` in the repo.
