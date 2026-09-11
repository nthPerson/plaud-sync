# Plaud Synced Notes — schema and taxonomy

Data source: `collection://bbc6c9aa-a96b-4501-a41a-8bd1b5a75866`
Database: `https://app.notion.com/p/61e12e128c7f473b94f22641d8a36260`

One page per recording. **The page body holds the full transcript**, which is why recall questions
are answered here rather than from the Plaud device (`plaud.md`).

## Schema

| Property | Type | Notes |
|---|---|---|
| `Name` | title | the exact Plaud recording title |
| `Date` | date | when it was recorded |
| `Area` | select | Personal · Academics · Work · Research |
| `Type` | select | Meeting · Reminder · Goal · Research · Dev · Client · Lecture · Coursework · Personal |
| `Project` | select | 16 options — below |
| `Tags` | multi-select | Meeting · Idea · Task · Follow-up · Personal |
| `Source Link` | url | `https://web.plaud.ai/file/<recording id>` — the durable join key |
| `Meeting Date` | date | set **only** when Type = Meeting; dashboards use it as the meeting timeline |
| `Tasks` | relation → Tasks | the action items extracted from this recording |
| `Synced` | created_time | automatic |

Body layout written by the sync: `## Summary`, `## Mind Map` (a synthesised Mermaid `mindmap` —
Plaud does not export one), `## Transcript`. Command recordings get Summary + Transcript only.

There is no `Reviewed` checkbox. One existed and was deliberately removed — Robert decided a review
workflow was maintenance he would never keep up with. Do not reintroduce one.

## Projects

The Notes DB carries all 16; the Tasks DB carries the same minus `Planner`.

| Project | Covers |
|---|---|
| `FAMAIL` | fairness-aware (multi-agent) imitation learning; GAIL, KDD paper, fairness metrics, FATE |
| `LARK` | merchant card-processing statement analysis; interchange, downgrades, ISOs, proposals, Sidekick AI |
| `Construction Diagram/Doc AI` | construction-document AI |
| `Car Sounds` | vehicle audio collection and automotive sound classification |
| `Caltrans` | driver-distraction research; outdoor advertising displays; the driving simulator |
| `Evidential Deep Learning` | construction digital twins, Scan-to-BIM, evidential DL for construction |
| `DiCE Lab` | the lab's **own** work — lab meetings, robotics, AR/VR/XR, field testing |
| `SCIBER-CT` | the NSF NRT traineeship — certificate, cohort, stipend/RCR, internship, hackathon, symposium |
| `BDA M.S.` | the **degree**: program of study, advising, candidacy, BDA 600/799A logistics, graduation |
| `GEOG 582` | Fall 2026 Intro to GIS Programming (Nara) |
| `COMPE 510` | Fall 2026 Machine Learning for Engineers (Xie) |
| `BDA 696` | Fall 2026 Process & Model Big Data (Lafler) |
| `Personal` | personal life — memos, health, goals, budgeting, travel, errands |
| `Unknown` | a work/academic/research note with **no** identifiable project |
| `Planner` | a recording that **issues commands** to the list or calendar — *Notes DB only* |
| `Plaud Sync` | work **on this automation** — prompts, watcher, planner, skills, cost, taxonomy |

## Tie-breakers

These decide the cases that actually recur:

- **`Area = Personal` ⇒ `Project = Personal`, never `Unknown`.** They are different fallbacks:
  `Personal` is a real project feeding the Personal Dashboard; `Unknown` is only for a
  work/academic/research note with no project, and feeds 📥 Unfiled Notes. Merging them was
  considered and rejected.
- **`Planner` vs `Plaud Sync`**: `Planner` issues commands ("mark the quiz done"); `Plaud Sync` is
  about building or changing the automation ("the sync prompt should stop duplicating events"). A
  recording that does both is `Plaud Sync`, and its instructions still get applied.
- **`SCIBER-CT` vs `DiCE Lab`**: classify by what the note is *about*. The traineeship program is
  SCIBER-CT; the research lab's own work is DiCE Lab. Dr. Akhavian leads both, so his presence
  decides nothing.
- **Course content vs certificate**: a specific course's lectures, assignments and exams file to
  that course's project. `COMPE 510` doubles as the SCIBER-CT ARX course, but its *content* is
  still `COMPE 510`; only traineeship-level business is `SCIBER-CT`.
- **Degree vs course vs thesis**: `BDA M.S.` is degree administration only. Course content goes to
  the course even when it satisfies an M.S. requirement; thesis *research* goes to its research
  project (e.g. `FAMAIL`), while thesis *admin* (committee, candidacy, defense scheduling) is
  `BDA M.S.`.
- **Prefer the most specific project.** A note about construction digital twins is
  `Evidential Deep Learning`, not `DiCE Lab`.

## Where notes surface

Project dashboards consume this DB through **linked views** filtered `Project = X`, each with a
`Type = Meeting` tab. There is deliberately no automation copying notes elsewhere — a `Routing`
property that once existed for that was removed. Do not reintroduce either.

`Planner` and `Plaud Sync` notes surface on the 📋 Planner page instead, as the **Command
recordings** and **Automation notes** linked views.

## Adding a project

Five places, and missing one fails silently — see `SKILLS-SPEC.md` §8.2 in the repo. The select
edit is the dangerous one: `ALTER COLUMN "Project" SET SELECT(...)` **replaces** the entire option
list, so every existing option must be re-listed with its colour, then re-fetched to confirm.
The two databases use *different colours for the same project*; preserve each one's.
