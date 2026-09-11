# Calendar

Google Calendar MCP, **primary calendar**, timezone `America/Los_Angeles`.

Calendar writes are **confirmed before they happen** (SKILL.md). State the resolved date and time,
then act. Task edits do not need this; calendar edits do.

## Meetings are not tasks

An appointment, call, meeting or event lives on the calendar and produces **no** task row. This is
a standing rule, not a preference — the headless channels follow it too, and violating it creates
duplicate work items that the planner then has to merge away.

Deadlines are the opposite case: a due date can be both a task and a mirrored event.

## Creating an event

| Field | Rule |
|---|---|
| Title | concise and specific; add the project in parentheses when it has one — "Ship recorders (Car Sounds)" |
| Time | as stated; **1 hour** when a time is given without a duration; **all-day** when no time is given |
| Location | "Zoom" or the named place |
| Description | ≤ 3 sentences of context, plus links to the Notion task/note it came from |
| Attendees | **none** unless an actual email address was given. Adding attendees sends invitations |

Check for a near-duplicate before creating. Do not create events for vague or undated mentions.

## Mirroring between tasks and events

- A task's mirrored event is recorded in its `Calendar Event` property (the event's `htmlLink`).
- **If a task's `Due` moves, move its linked event too**, keeping it all-day or timed as it was.
- A task going **Done keeps its event** as history.
- A task **Dropped** may have its event deleted — but only under the evidence rule below, and
  `Calendar Event` must be cleared once it is.

## The evidence rule

Robert's standing policy, stated 2026-09-03: **remove on good evidence, never on a hunch.** It
governs every deletion, from every channel. The autonomous planner run never deletes anything at
all.

Delete an event only when one of these holds:

1. **A task's linked event** — and only when the request explicitly drops, cancels or removes
   *that* task, by ID or unambiguous description, and the event is the one in its `Calendar Event`.
2. **A named event** — and only when exactly **one** event matches both its title words and its
   date or window. Search today − 7 to + 45 days unless the request implies otherwise.
3. **Never an event with attendees other than Robert**, unless the request explicitly cancels the
   meeting *with them* — deleting sends cancellations to real people. Otherwise report
   "has attendees" and stop.
4. **Never on similarity alone.** When two candidates fit, delete neither, and say which two you
   saw.

## Resolving dates

Against the **source's** date — a recording's "next Thursday" is relative to the recording, an
email's to the email, a chat message's to now. A weekday name means the coming one; "next
<weekday>" means that weekday in the following calendar week; "next week" means next Monday.

Always state the resolved absolute date in the confirmation, so a misread costs one follow-up
rather than a wrong meeting.

## Useful reads

- `list_events` over an explicit range for "what does my week look like".
- `search_events` when matching an event by title before moving or deleting it.
- Deadlines with **no** mirrored event are worth surfacing: read the Upcoming view, check each
  row's `Calendar Event`, and report the hard deadlines that are invisible on the calendar.
