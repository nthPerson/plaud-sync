# SKILLS-SPEC.md

Design for the Claude **skills** that let an interactive session — in Claude Chat on the phone or
Claude Code at the desk — query, change and maintain what `plaud-sync` and the planner produce.

Status: agreed 2026-09-10, not yet built. Read `CLAUDE.md` and `PLANNER-SPEC.md` first; this
document assumes both.

## 1. Why

Three channels already *write* to the task list: the sync prompt (voice), the commands prompt
(email), and the planner (autonomous). Nothing lets a human ask it questions, and the run data
says questions are what's missing:

| Signal (2026-09-04 → 09-10) | Number |
|---|---|
| Open tasks | 26 → **45** |
| Items overdue 4+ days | **5** (Car Sounds Task-37, LARK Task-48/49, …) |
| Tasks created vs completed, last 7 days | ~14 created, ~8 closed |
| Sync cost, mean of last 10 runs | **$2.17** (`CLAUDE.md` still claims a $0.59 baseline) |
| Combined burn, 7-day mean | **$8.19/day** |

Capture is solved. **Closure is not.** The skills exist to make review, triage and closure as
cheap as capture already is — and to stop the ops numbers in `CLAUDE.md` from drifting unchecked.

## 2. Two skills

| Skill | Surfaces | Tools it may assume | Source of truth for |
|---|---|---|---|
| **`plaud-sync-planner`** | Claude Chat **and** Claude Code, every machine | Notion, Google Calendar, Plaud | The data: tasks, notes, events |
| **`plaud-sync-ops`** | Claude Code, in this repo | Bash, Read/Edit, the above | The machine: services, logs, prompts, cost |

Both names carry the `plaud-sync-` prefix so their association with this repo is obvious from
outside it — in a `~/.claude/skills/` listing, or in the skill picker on claude.ai.

`plaud-sync-planner` is **pure Markdown**. Claude Chat's code sandbox has no connector access, so
a script there could never reach Notion; anything executable belongs in `plaud-sync-ops`.

How each one reaches the machines it needs to be on is §6.

## 3. Decisions

Agreed 2026-09-10 (1–4) and 2026-09-11 (5–7).

1. **Two skills, split data vs machine.** A Chat copy that carries systemd instructions goes stale
   every time the unit changes and can never act on them.
2. **Task edits apply immediately; calendar writes are confirmed first.** The email and voice
   channels already apply task changes headlessly — an interactive session asking permission for
   the same edit would be slower than replying `done Task-17` to the brief, which defeats the
   purpose. Calendar creates, moves and deletes are read back before they happen, because an
   interactive session *can* ask and the evidence rule exists precisely there.
3. **Manual edits are logged to the Command Log**, like every other channel, under a new
   `Claude session` option on `Channel` (see §8). Without it, changes made from the phone appear
   in no audit trail and the next brief's "Applied since the last run" under-reports.
4. **Read path: view mode by default, `rows` mode for narrow lookups, SQL never.** View mode is
   documented quota-free on every plan. `rows` mode (structured `filter`/`sort`/`limit`, added to
   the Notion MCP after all three prompts were written) was tested working on 2026-09-10 and is
   far cheaper for a targeted question — but its metering is *unstated* in the tool docs, so it is
   not trusted for the wide reads. On any quota error, fall back to the matching view.
5. **Both skills are named `plaud-sync-*`**, so their association with this repo is legible from a
   skills listing on any machine or in the claude.ai picker.
6. **Git is the source of truth; syncthing is the delivery; the repo itself is never synced** (§6).
   The ops skill becomes a *project* skill, since it needs the repo and, for half its procedures,
   the service host's git-ignored run logs.
7. **The Plaud connector in Chat changes what is *possible*, not what is *preferred*** (§4.4).
   Recall stays on Notion for context economy; the connector earns its place upstream, on
   reconciliation.

## 4. `plaud-sync-planner`

```
skills/plaud-sync-planner/
  SKILL.md              version stamp · object map · invariants · operation → reference dispatch
  reference/tasks.md    schema, write formats, field ownership, Source Key grammar, view table
  reference/notes.md    Plaud Synced Notes schema, taxonomy, tie-breakers (condensed from the prompt)
  reference/calendar.md event conventions, task↔event mirroring, the evidence rule
  reference/plaud.md    the five Plaud tools, the one-call rule, reconciliation
  reference/recipes.md  the standard operations, each with its exact call
  reference/grooming.md weekly review, merge protocol, integrity sweep
```

Frontmatter description must fire on the vocabulary actually used in a phone question — task,
to-do, due, overdue, what should I work on, `Task-<n>`, defer, drop, reschedule, "what did I say
in that meeting" — not on the word "plaud", which Robert rarely types.

### 4.1 Invariants (SKILL.md, stated once, referenced everywhere)

- **`Source Key` is the dedup key.** Never create a task without checking for one first.
- **`Priority`, `Score` and `Why now` belong to the planner.** Never hand-score. After changing
  `Due` or `Status`, write one interim `Why now` sentence ("Deferred to Sep 30 — re-ranked at the
  next planner run") so the Today view never shows a stale reason.
- **`Manual Priority` is Robert's**, and the planner may only deviate from it with an explanation.
- **Meetings are never tasks.** They live on the calendar.
- **Deletion follows the evidence rule** (`PLANNER-SPEC.md` §15.2) — on good evidence, never a hunch.
- **Never hand-edit the ☀️ Today page.** Every planner run replaces its body. Durable notes go on
  a task or the Planner page callout.
- **Notion page URLs are `app.notion.com/p/<id>`.** The bare form 404s.
- **Never call `get_file` to answer something Notion can answer.** It returns the entire
  transcript every time — see §4.4.
- **Relative dates resolve against the source's date**, not today's, in `America/Los_Angeles`.
- **Read the narrowest view that answers the question** (§4.2). Page with `start_cursor` past 100
  rows — 45 open today, and the cap is real.

### 4.2 The view table (measured 2026-09-10, all on database `b1c52e69d3924aea8962bee32440ffbe`)

| View | `?v=` id | Contents | Use for |
|---|---|---|---|
| **Today** | `3d1eb306511081a1aff6000cb284338f` | Next + In progress, un-snoozed, Score desc | "what's on my plate" — **not** filtered to today |
| **Open** | `3d1eb306511081a5a601000c7530ed1a` | everything not Done/Dropped | dedup, grooming, the prompts' read |
| **Upcoming** | `3d1eb306511081e1a5f3000cdd7d35e6` | open with a Due, by Due | deadlines |
| **Waiting** | `3d1eb306511081fb954d000c6a0e181b` | Status = Waiting | who owes what |
| **Inbox** | `3d1eb3065110814aa2af000c505101b4` | Status = Inbox, newest first | decide-or-drop |
| **Done** | `3d1eb30651108120a718000c760c0de9` | Done + Dropped, newest first | "what did I finish" |
| **By project** | `3d1eb306511081d3a0c1000c9edc061f` | board, grouped by Project | project pulse |
| **Calendar** | `3d1eb306511081fa90f9000c35c291f8` | by Due | month view |

Ids are the dash-stripped view UUIDs from a `notion-fetch` of the database; copy them, never
retype them.

### 4.3 Recipes

Query: **R1** what's on my plate · **R2** overdue and slipping · **R3** this week's deadlines and
agenda, including hard deadlines with no calendar event · **R4** project pulse (open tasks +
recent notes for one project) · **R5** recall from a recording · **R6** trace a task to its source.

R6 decodes the `Source Key` grammar: `plaud:<file id>:<n>` → `https://web.plaud.ai/file/<file id>`;
`canvas:<type>:<id>`, `gcal:<event id>`, `email:<Message-ID>`, `manual:<…>`. **In `rows` mode the
colons come back backslash-escaped** (`plaud\:c76bda…\:1`) — unescape before matching.

Modify: **R7** done / defer / snooze / drop / start / waiting / priority / note — semantics copied
verbatim from `planner-commands-prompt.txt` so all four channels behave identically · **R8** add a
task (`Source` = Manual, `Source Key` = `manual:<date>:<n>`) · **R9** schedule / move / cancel an
event · **R10** fix a misfiled note (the note page *and* the tasks it produced).

`Task ID` is an `auto_increment_id` — **read-only**. A session that creates a task must re-fetch
the page to learn the code, or say nothing rather than guess it.

Maintain: **R11** merge duplicates (keep the older row, sum `Mentions`, union `Notes`, newer row →
Dropped with "merged into Task-*n*") · **R12** weekly review · **R13** integrity sweep · **R14**
log the session to the Command Log.

### 4.4 Plaud access, and why recall still goes through Notion

A **Plaud connector now exists in the Claude Desktop app** (authenticated 2026-09-11), exposing the
same five tools as the MCP on this box: `list_files`, `get_file`, `get_note`, `get_transcript`,
`get_current_user`. Chat is no longer Notion-only.

Recall (R5) should still go through Notion, but for a better reason than availability: **the full
transcript is already in the note page**, and `get_file` returns the entire transcript
unconditionally (`CLAUDE.md`). Answering "what did Reza actually ask for?" from Plaud means pulling
a whole recording into context to find one sentence; a Notion search returns the page. The
one-call rule applies as ever — `get_note` and `get_transcript` are strict subsets of `get_file`.

What the connector genuinely adds is everything *upstream* of Notion:

**R15 — reconcile Plaud against Notion.** `list_files` over a date window, compared against the
Notes DB by `Source Link` (`https://web.plaud.ai/file/<id>`), reporting recordings with no page.
Until now the only signal that a recording was consumed without syncing was the failure email —
13 runs failed that way between 07-23 and 08-18, each marked `\Seen` and processed regardless.
This makes the gap visible from the phone, which is where you'd notice it.

**Non-goal: filing a recording from Chat.** It would need the sync prompt's 326 lines of taxonomy
as a second copy, drifting against the original from the day it was written. Chat detects the gap;
the watcher or `/replay-note` fills it.

### 4.5 R13 — the integrity sweep

One pass, all from the Open and Done views: Done/Dropped rows with no `Completed`; `Snoozed Until`
in the past; duplicate `Source Key`s; `Calendar Event` URLs whose event no longer exists; tasks
with `Source` = Plaud but an empty `Notes` relation; notes with `Type` = Meeting and no
`Meeting Date`; open rows with no `Due` untouched for 21 days.

## 5. `plaud-sync-ops`

```
.claude/skills/plaud-sync-ops/
  SKILL.md                  runbook index, the host check, and the traps
  scripts/runstats.py       cost, success rate, task churn, backlog trend — both run logs
  scripts/check-drift.py    prompt option lists ↔ live Notion selects ↔ skill reference
  reference/procedures.md   restart rules, replay, prompt edits, taxonomy changes
```

It ships as a **project** skill, inside the repo, so it arrives with `git clone` and needs no
install anywhere. But half of it only works where the data is: `runstats.py` and every cost or
health procedure need the run logs, which are git-ignored and therefore exist **only on the
service host — `bg-pc`, whose hostname is `lark-server`** (§6). SKILL.md opens with a host check
(`systemctl is-active plaud-sync`) and must say "not the service host — run logs are on
bg-pc/lark-server" rather than reporting an empty history as a clean bill of health. Prompt edits,
taxonomy changes and the drift check work on any clone.

`runstats.py` replaces the ad-hoc one-liners in `/sync-health` and gives it a baseline that is
recomputed rather than quoted from a doc written in July. `check-drift.py` catches the
two-edit failure recorded in `CLAUDE.md` (a `Project` listed in the prompt but absent from the
Notion select) automatically, and now also covers a third copy — the skill's own reference.

Traps to encode, each already paid for once: the sync prompt is read at startup so editing it
needs a restart, while `planner-commands-prompt.txt` is read per use and does not · MCP **write**
tools in `settings.json`'s `ask` list silently stall the headless watcher · the venv interpreter,
never system Python · `systemctl start planner@<mode>` blocks for minutes by design.

## 6. Distribution across machines

Measured 2026-09-11. There are **three machines: thinkpad, mf-pc, bg-pc** — and *`bg-pc` is the
machine whose hostname is `lark-server`*. Same box, two names: syncthing knows it as `bg-pc`,
`hostname` and every systemd/journal command call it `lark-server`. It is the one running the
watcher and the planner timers, so the service host is also a daily-driver dev machine, not a
separate server. Anything written about "the service host" means this one under either name.

The repo has a GitHub remote (`nthPerson/plaud-sync`) reachable from all three. Synced folders are
`~/sync/claude-sessions` (transcripts, in use) and `~/sync/workbench` (new, one file in it).

**The mesh is a star, and should be a triangle.** thinkpad shares both folders with bg-pc and
mf-pc; bg-pc and mf-pc each share only back to thinkpad. Syncthing propagates transitively, so all
three converge today and all three read "Up to Date" — this is not currently broken. But every
exchange between bg-pc and mf-pc routes through thinkpad, which is the newest laptop and the one
most likely to be closed or away, while bg-pc is the always-on service host: the pair most likely
to both be running is the only pair that cannot talk directly. And if thinkpad were lost, bg-pc
and mf-pc would drift while both still displayed "Up to Date", each being genuinely current with
respect to every peer it knows of. A green status that means "current with a dead hub" is the
silent-drift failure this whole section exists to prevent.

Closing it is four checkboxes, since sharing is pairwise and both ends must list each other: on
bg-pc add **mf-pc**, on mf-pc add **bg-pc**, for each of the two folders. Both machines already
hold the folders under matching ids, so this completes an existing pair rather than offering a new
folder. All three are `sendreceive`; there is no send-only asymmetry to preserve.

**`plaud-sync-planner` ships by syncthing, out of git.** Git stays the source of truth — review,
history, and something for `check-drift.py` to compare against; syncthing is only delivery:

```
skills/plaud-sync-planner/          edited, reviewed, committed here
         ↓   skills/publish.sh  (rsync + dated zip)
~/sync/workbench/claude-skills/     syncthing propagates in seconds
         ↓   one symlink per machine, once
~/.claude/skills/plaud-sync-planner
```

Each machine is configured exactly once
(`ln -s ~/sync/workbench/claude-skills/plaud-sync-planner ~/.claude/skills/`) and never again: a
change published from any machine is live on all of them without a pull, which is the property
you asked for.

**Do not put the repo itself in a synced folder.** Every runtime file is git-ignored for good
reason — `runs.jsonl`, `planner-runs.jsonl`, `planner-state.json`, `processed.json` are
single-writer state belonging to the service host, and `.env` holds the Gmail app password and the
Canvas token. Replicating those to the other two machines spreads the secrets and invites a second
writer; `processed.json` in particular is the only thing standing between a UID and a reprocess
loop. Git already distributes the parts that should travel.

Two guards on the synced copy:

- Add `*.sync-conflict-*` to `~/sync/workbench/.stignore`. A simultaneous edit otherwise leaves
  `SKILL.sync-conflict-20260911-….md` sitting inside a skill directory, which is precisely the
  kind of stray file you don't want a loader to find.
- The published copy is read-only on dev machines. Edits go through the repo, always.

**Claude Chat is the one endpoint that cannot sync.** Skills there are uploaded, so every change
needs a re-upload; `publish.sh` drops a dated zip beside the skill so it is on whatever machine
you happen to be sitting at. Two design consequences:

1. Keep the portable skill's content **slow-moving**. Anything volatile — cost baselines, ids that
   might be re-created, anything measured — belongs in `plaud-sync-ops` or the repo, not in the
   copy that costs a manual upload to correct.
2. **Stamp a version** on SKILL.md's first line (`skill-version: 2026-09-11`), with an instruction
   to report it when asked. Then "which version does Chat have?" is answerable in one question
   instead of guessed at, and `check-drift.py` has something to check against.

## 7. Build order

Built 2026-09-11.

1. ✅ `skills/plaud-sync-planner/` — SKILL.md + six references, ids copied from live fetches.
2. ✅ Notion: the three changes in §8, the five-place `Plaud Sync` rollout, Task-84 moved onto it.
3. ✅ `.claude/skills/plaud-sync-ops/` + both scripts; `/sync-health` now calls `runstats.py`.
4. ✅ Syncthing triangle closed (by Robert). `skills/publish.sh` written and run; published to
   `~/sync/workbench/claude-skills/`, symlinked into `~/.claude/skills/` on bg-pc, zip built.
   ⬜ Remaining: symlink on **thinkpad** and **mf-pc**, and upload the zip to **claude.ai**.
5. ✅ `CLAUDE.md` cost baseline corrected to the measured figures, with a pointer to `runstats.py`
   so the next reader recomputes instead of quoting.
6. ⬜ Exercise: five real questions from the phone, one R15 reconcile, and one grooming pass on the
   stuck overdue items (Task-37, Task-48, Task-49, …).

`runstats.py` on the day of the build: 77 runs over 70 recordings, 83 % ok, mean **$1.79**, last-10
**$2.28**, burn **$8.97/day**, open tasks **27 → 46 over 14 planner runs**, and **six recordings
that never synced on any attempt** (uids 13, 32, 33, 34, 35, 37) — the last of which no existing
tool surfaced.

## 8. Notion changes

Every select edit here carries the same hazard: `ALTER COLUMN … SET SELECT(...)` **replaces** the
whole option list. Re-list every existing option with its colour, then re-fetch to confirm nothing
was dropped.

### 8.1 `Claude session` on the Command Log

Add to the `Channel` select (`collection://f91d236c-b7d9-4abe-82ca-f0ab28f5288b`), keeping Voice ·
Email reply · Email subject · Email free text · Planner run.

### 8.2 `Plaud Sync` — a Project for the automation itself

Task-84 had to be filed `Personal / Personal` because none of the options fits work *on*
plaud-sync, and that stream is now real: this skills build, the rows-mode migration, cost work.
Left alone it pollutes the Personal Dashboard with infrastructure.

Named after the system, the way `FAMAIL` and `LARK` are. **It must not blur into `Planner`**, and
the prompts state the line explicitly:

| Option | Means | Lives on |
|---|---|---|
| `Planner` | a recording whose purpose is to *issue commands* to the list or calendar | Plaud Notes DB only |
| `Plaud Sync` | work *on the automation* — prompts, watcher, planner, skills, cost, taxonomy | **both** DBs |

`Plaud Sync` goes on the Tasks DB as well as the Notes DB, which is the difference from `Planner`:
commands are not tasks, but building the thing that runs them certainly is. Area for both is
`Personal` — it is Robert's own infrastructure, not work, school or research.

Adding it touches **five** places, one more than the "two edits" `CLAUDE.md` warns about, and the
count is itself the argument for `check-drift.py`:

1. `Project` select on the Tasks data source (14 → 15 options)
2. `Project` select on the Plaud Notes data source (15 → 16 options)
3. `plaud-sync-prompt.txt` — the option list, its gloss, and a tie-breaker against `Planner`
4. `planner-prompt.txt` — a project weight in the Step 4 scoring table (Medium, +5: real work,
   rarely deadline-bound)
5. `planner-commands-prompt.txt` — the hardcoded "one of the 14 options" count

Then `CLAUDE.md` and `PLANNER-SPEC.md` §4 need their Project lists corrected, and Task-84 moves
onto the new option.

### 8.3 The linked view on the Planner page

The 📋 Planner page (`3d1eb3065110819fa358d3af8a3158b8`) is the hub for managing the automation,
so the new project's notes surface there rather than on a dashboard of their own: a linked view of
Plaud Synced Notes filtered `Project = Plaud Sync`, beside the existing **Command recordings**
view (`Project = Planner`). Page order becomes callout → Today → Tasks → Command Log → Command
recordings → **Automation notes**. Both databases stay *inline* — that is load-bearing, since
inline is what shows all their views on the page.

## 9. Tracked elsewhere, and later

Teaching the three production prompts to read in `rows` mode instead of pulling the whole Open
view is now **Task-84** (created 2026-09-11, Effort L). It is the biggest single cost lever
available — that read is the dominant input in every run, against a 7-day mean of $8.19/day — and
it needs its own before/after measurement, so it stays out of this build rather than riding along
untested. The skills should be written to the efficient pattern from the start (§4.1's
narrowest-view rule, §4.4's one-call rule) so they are not part of the problem being fixed.

Still later:

- The Artifact dashboard from `PLANNER-SPEC.md` §13, now that a skill defines the read/write rules
  a page would follow.
- A `/groom` slash command in Code, if R12 turns out to be something Robert runs rather than asks for.
