---
name: plaud-sync-planner
description: Query and maintain Robert's Notion task list, Plaud meeting notes, and Google Calendar — the artifacts the plaud-sync automation produces. Use for tasks, to-dos, deadlines, what is due or overdue, what to work on now, Task-<n> codes, completing / deferring / dropping / adding work, scheduling or moving calendar events, weekly review and backlog grooming, and recalling what was said in a recorded meeting or lecture.
---

<!-- skill-version: 2026-09-11 -->

# Plaud Sync — planner

Robert records meetings and memos on a Plaud device. An automation files each recording into
Notion, extracts action items into a **Tasks** database, and a planner run ranks them twice a day
and rewrites a **Today** page. This skill is how a conversation reads and changes that system.

**Report `skill-version` above when asked which version of this skill is loaded.** The Claude Chat
copy is uploaded by hand and can lag the repo; that stamp is the only way to tell.

## What this operates on

| Object | Address |
|---|---|
| Tasks data source (write here) | `collection://be0b1624-4ea6-43dd-acc2-3a828a8ab07e` |
| Tasks database (views live here) | `b1c52e69d3924aea8962bee32440ffbe` |
| Plaud Synced Notes data source | `collection://bbc6c9aa-a96b-4501-a41a-8bd1b5a75866` |
| Command Log data source | `collection://f91d236c-b7d9-4abe-82ca-f0ab28f5288b` |
| 📋 Planner page (the hub) | `https://app.notion.com/p/3d1eb3065110819fa358d3af8a3158b8` |
| ☀️ Today page (planner-owned) | `https://app.notion.com/p/3d1eb30651108180942dff91930bdd10` |
| Calendar | Google Calendar MCP, primary calendar, `America/Los_Angeles` |

## Invariants

These hold for every operation. Breaking one corrupts state that three headless automations also
write to.

1. **`Source Key` is the dedup key.** Never create a task without checking whether one exists.
   Grammar and decoding: `reference/tasks.md`.
2. **`Priority`, `Score` and `Why now` belong to the planner run.** Never hand-score. After
   changing `Due` or `Status`, write one interim `Why now` sentence — "Deferred to Sep 30 —
   re-ranked at the next planner run" — so the Today view never shows a stale reason.
3. **`Manual Priority` is Robert's**, not yours. Set it when he asks; never overwrite it silently.
4. **Meetings are not tasks.** An appointment, call or event goes on the calendar only.
5. **Deletion follows the evidence rule** — remove on good evidence, never on a hunch.
   `reference/calendar.md` states it in full. It is Robert's standing policy, not a default.
6. **Never hand-edit the ☀️ Today page.** Every planner run replaces its body wholesale. Anything
   that must persist goes on a task or the Planner page callout.
7. **Notion page URLs are `app.notion.com/p/<id>`.** The bare `app.notion.com/<id>` form 404s.
8. **Relative dates resolve against the source's date**, not today's — a recording's instruction
   resolves against the recording date. Weekday names mean the coming one; "next <weekday>" means
   the following calendar week. Timezone is `America/Los_Angeles`.
9. **Read the narrowest view that answers the question**, and never call `get_file` for something
   Notion already holds. Both rules exist to keep context small; see below and `reference/plaud.md`.

## Reading: cheapest path first

SQL mode on `notion-query-data-sources` is **metered on this workspace** and has been refused in
production. Do not use it.

1. **A named view** (`{"mode":"view","view_url":…}`) — documented quota-free on every plan. This is
   the default. The view table is in `reference/tasks.md`; pick the narrowest one that fits.
2. **`rows` mode** with a structured `filter`/`sort`/`limit` — best for a targeted lookup ("open
   hard deadlines before Friday"). Verified working 2026-09-10, but its quota status is *unstated*
   in the tool docs, so it is the second choice, not the first. On any quota error, fall back to
   the matching view.
3. **SQL — never.**

Page with `start_cursor` while `has_more` is true; a view returns at most 100 rows and the open
list is already in the forties.

For "what should I work on", **read the ☀️ Today page first** — the planner wrote it hours ago and
it is one fetch. Only re-derive from the Tasks DB if it is stale or the question needs something it
does not show.

## Writing: what applies immediately, what gets confirmed

- **Task edits apply immediately** — done, defer, snooze, drop, start, waiting, priority, note,
  add. The email and voice channels already do this headlessly; asking permission here would make
  the assistant slower than replying `done Task-17` to the morning brief.
- **Calendar writes are read back before they happen** — creating, moving, or deleting an event.
  State what you are about to do, with the resolved date and time, and wait. An interactive session
  *can* ask, and the evidence rule exists exactly here.
- **Always state the resolved date** in any confirmation ("deferred to Mon 15 Sep"), so a misread
  is correctable with one follow-up.

After any run that changed something, **write one Command Log row** with `Channel` =
`Claude session`. Format in `reference/tasks.md`. This is what keeps the Planner page a complete
history and stops the next brief's "Applied since the last run" from under-reporting.

## Where to look

Load only what the task needs.

| The question | Read |
|---|---|
| Task schema, write formats, view table, Source Key, Command Log row | `reference/tasks.md` |
| Which project/area a note or task belongs to; the note page layout | `reference/notes.md` |
| Event conventions, task↔event mirroring, the evidence rule | `reference/calendar.md` |
| Anything touching the Plaud device or recordings directly | `reference/plaud.md` |
| Step-by-step for a standard operation (R1–R15) | `reference/recipes.md` |
| Weekly review, merging duplicates, integrity sweep | `reference/grooming.md` |

## Operating notes

- **Task codes are `Task-<n>`** and `Task ID` is auto-assigned and read-only. After creating a
  task you must re-read the row to learn its code — do not guess or predict it.
- **Ambiguity is reported, never guessed.** If two rows match a description equally well, change
  neither and say which two. This mirrors the headless channels' `unresolved` behaviour.
- **The backlog is the standing problem.** Open tasks grew 26 → 45 in the first week of September
  2026 while five sat overdue for days; capture works, closure does not. When a question invites
  it, prefer helping Robert close or drop things over helping him add more.
- The system files itself from three other channels — voice, email, Canvas. If something looks
  already-handled, it may well be; check before duplicating it.
