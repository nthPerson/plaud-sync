# Tasks — schema, views, write formats

Data source: `collection://be0b1624-4ea6-43dd-acc2-3a828a8ab07e`
Database (views): `b1c52e69d3924aea8962bee32440ffbe`

## Views — read through these

Every URL is `https://www.notion.so/b1c52e69d3924aea8962bee32440ffbe?v=<id>`.

| View | `<id>` | Shows | Use for |
|---|---|---|---|
| **Today** | `3d1eb306511081a1aff6000cb284338f` | Next + In progress, un-snoozed, Score desc | "what should I work on" |
| **Open** | `3d1eb306511081a5a601000c7530ed1a` | everything not Done/Dropped | dedup, grooming |
| **Upcoming** | `3d1eb306511081e1a5f3000cdd7d35e6` | open rows with a Due, by Due | deadlines |
| **Waiting** | `3d1eb306511081fb954d000c6a0e181b` | Status = Waiting | who owes what |
| **Inbox** | `3d1eb3065110814aa2af000c505101b4` | Status = Inbox, newest first | decide-or-drop |
| **Done** | `3d1eb30651108120a718000c760c0de9` | Done + Dropped, newest first | "what did I finish" |
| **By project** | `3d1eb306511081d3a0c1000c9edc061f` | board grouped by Project | project pulse |
| **Calendar** | `3d1eb306511081fa90f9000c35c291f8` | calendar by Due | month view |

**The `Today` view is not filtered to today.** It is the whole ranked open list. The actual
day-shaped answer is the ☀️ Today *page*, which the planner writes.

Call shape:

```json
{"mode": "view", "page_size": 100,
 "view_url": "https://www.notion.so/b1c52e69d3924aea8962bee32440ffbe?v=3d1eb306511081a1aff6000cb284338f"}
```

## Schema

| Property | Type | Notes |
|---|---|---|
| `Name` | title | imperative, ≤ 80 chars, no trailing period |
| `Task ID` | auto_increment_id | **read-only.** Robert types it as `Task-<n>` |
| `Status` | select | Inbox · Next · In progress · Waiting · Done · Dropped |
| `Priority` | select | P0–P3 — **planner-owned** |
| `Manual Priority` | select | P0–P3 — **Robert's**; the planner may deviate but must explain |
| `Score` | number | 0–100 — **planner-owned** |
| `Why now` | text | one sentence — planner-owned, but set an interim one after any Due/Status change |
| `Due` | date | with time when the source gave one |
| `Hard deadline` | checkbox | true for submissions, registrations, cutoffs, promised deliveries |
| `Area` | select | Personal · Academics · Work · Research |
| `Project` | select | 15 options — see `notes.md`. **`Planner` is never a task's project**; `Plaud Sync` is |
| `Effort` | select | XS ≤15 min · S ≤1 h · M half day · L multi-day |
| `Source` | select | Plaud · Canvas · Calendar · Email · Manual |
| `Source Key` | text | the dedup key — see below |
| `Source Link` | url | Plaud file URL, Canvas item URL, calendar htmlLink, or empty |
| `Notes` | relation → Plaud Notes | recordings that mentioned this task; first = origin |
| `Command Log` | relation → Command Log | every command that touched it |
| `Mentions` | number | distinct sources referencing it; feeds the score |
| `Calendar Event` | url | htmlLink of the mirrored event, if any |
| `Context` | text | 1–3 sentences so the task is self-explanatory |
| `Waiting On` | text | who blocks a `Waiting` task |
| `Snoozed Until` | date | hidden from Today until then; the planner clears it once past |
| `Completed` | date | set when the row first goes Done |
| `Created` / `Edited` | auto | |

## Write formats

These are the ones that are easy to get wrong:

- **Dates**: `"date:Due:start": "2026-09-30"` plus `"date:Due:is_datetime": 0` (or `1` with a time).
  Same shape for `Completed`, `Snoozed Until`.
- **Checkboxes**: `"Hard deadline": "__YES__"` / `"__NO__"`.
- **Relations**: an array of page URLs — `"Notes": ["https://app.notion.com/p/<id>"]`.
- **Clearing a field**: `null`.
- **Selects**: the exact option string, including case and punctuation (`BDA M.S.`, not `BDA MS`).

## `Source Key` grammar

| Source | Key | Decodes to |
|---|---|---|
| Plaud | `plaud:<file id>:<n>` | `https://web.plaud.ai/file/<file id>` |
| Canvas | `canvas:<type>:<id>` | the Canvas item |
| Calendar | `gcal:<event id>` | the event |
| Email | `email:<Message-ID>` | the forwarded mail |
| Manual | `manual:<date>:<n>` | nothing — created by hand |

**The colons come back backslash-escaped** — `plaud\:c76bda…\:1` — in **both** view mode and rows
mode (verified 2026-09-11). Always unescape before comparing, or every dedup check silently misses
and you create a duplicate.

## Creating a task by hand

```
Name          imperative, ≤ 80 chars
Status        "Next" when clearly actionable; "Inbox" when ownership or actionability is unclear
Due           absolute date, or empty — do not invent a deadline Robert did not state
Hard deadline "__YES__" only for a real cutoff
Area, Project per notes.md
Effort        XS / S / M / L
Source        "Manual"
Source Key    manual:<YYYY-MM-DD>:<n>
Mentions      1
Context       1–3 sentences: what it is and who expects it
```

Leave `Priority`, `Score`, `Why now`, `Calendar Event`, `Waiting On`, `Snoozed Until` and
`Completed` empty — the planner owns them. Then re-read the row to learn its `Task-<n>` code.

## The Command Log row

One row per session that changed anything. Data source
`collection://f91d236c-b7d9-4abe-82ca-f0ab28f5288b`.

```
Name        "Claude session: <≤ 60-char summary>"
Time        now — "date:Time:start" with "date:Time:is_datetime" 1
Channel     "Claude session"
Result      "Applied" when nothing was left unresolved, else "Partial", else "Nothing"
Command     what Robert actually asked, ≤ 1000 chars
Applied     number of tasks changed
Created     number of tasks created
Calendar    number of calendar changes
Unresolved  anything skipped and why, joined with "; "
Details     one line per change
Tasks       relation to every task row touched
```

`Channel` options are Voice · Email reply · Email subject · Email free text · Planner run ·
**Claude session**. Use the last one; the others belong to the headless channels.
