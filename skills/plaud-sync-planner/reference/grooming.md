# Grooming — review, merge, integrity

The standing problem this file exists for: **the list captures well and closes badly.** Open tasks
went 26 → 45 in the first week of September 2026; five sat overdue for four days straight while new
ones kept arriving from four channels. Nothing is broken — closure just has no automation behind
it, because only Robert can decide.

So the goal of a grooming pass is *fewer open rows*, not a tidier database.

---

## R12 — Weekly review

One pass, roughly this order. Read the **Open view** once and work from it.

**1. Close what's actually done.** Anything Done or Dropped with an empty `Completed` gets today's
date. Then ask about rows that look finished — a task whose meeting has passed, a deliverable whose
deadline is a week gone. The overdue list is mostly this.

**2. The overdue list, one at a time.** For each row overdue by more than a couple of days, the
question is close / defer to a real date / drop. Do not let it pass with "still overdue" — that is
how a row reaches its fourth consecutive brief. If Robert defers without a date, `Snoozed Until` =
tomorrow rather than a fabricated `Due`.

**3. Decide or drop.** Two populations:
- `Inbox` rows older than 14 days — they never got a decision.
- Open rows with **no `Due`** and no activity for 21 days.

List them with their code and why they qualify. Dropping is a success, not a failure; an honest 20
open rows beats a decorative 45.

**4. Waiting rows.** List each with who it waits on and how long. Anything waiting more than two
weeks is usually a nudge to send or a task to drop.

**5. Duplicates.** Scan for rows describing the same deliverable from different sources — a Canvas
quiz a lecture recording also produced, an email repeating a calendar deadline. Merge per R11.

**6. Report, then log.** Summarise what changed, then write **one** Command Log row for the whole
pass.

Do not re-score anything. The next planner run recomputes `Priority` and `Score` from whatever
state you leave behind.

---

## R13 — Integrity sweep

Checks that catch silent corruption. All answerable from the Open and Done views plus a little
calendar reading.

| Check | Why it matters |
|---|---|
| Done/Dropped with empty `Completed` | breaks "what did I finish this week" |
| `Snoozed Until` in the past | the row is hidden from Today but should not be |
| Duplicate `Source Key` values | means dedup failed; two rows for one deliverable |
| `Calendar Event` pointing at a deleted event | a dead link the planner will keep mirroring |
| `Source` = Plaud but empty `Notes` relation | lost its provenance; the recording can't be found |
| Note with `Type` = Meeting and no `Meeting Date` | drops off the project dashboards' meeting timeline |
| Open rows approaching 100 | view mode pages at 100; past that, reads silently truncate without `start_cursor` |

The last one is a real horizon, not a hypothetical — the open count was 45 and climbing in
September 2026.

---

## What not to do

- **Do not rewrite the ☀️ Today page.** The next planner run replaces it wholesale, so any hand
  edit is both invisible and lost.
- **Do not hand-score.** `Priority` and `Score` are planner-owned; an interim `Why now` sentence is
  the correct way to explain a change you made.
- **Do not bulk-drop to hit a number.** Each drop is a decision Robert makes; propose them, act on
  the answer.
- **Do not reintroduce a `Reviewed` checkbox** on the Notes DB. One existed and was removed
  deliberately — it was maintenance he would never keep up with.
