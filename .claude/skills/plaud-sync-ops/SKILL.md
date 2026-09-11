---
name: plaud-sync-ops
description: Operate and troubleshoot the plaud-sync machine itself — the IMAP watcher service, planner timers, headless Claude runs, run logs, cost and token spend, prompt edits, and taxonomy changes. Use when the sync or planner misbehaves, a recording did not get filed, a run needs replaying, costs need checking, or a Project option or prompt needs changing.
---

<!-- skill-version: 2026-09-11 -->

# Plaud Sync — ops

The machine, not the data. For questions about tasks, notes, deadlines or the calendar, use
**plaud-sync-planner** instead.

## Check the host first

Half of this skill only works where the data is. `runs.jsonl`, `planner-runs.jsonl`,
`planner-state.json` and `processed.json` are **git-ignored and single-writer** — they exist only
on the service host, which is **`bg-pc`, whose hostname is `lark-server`** (same machine, two
names; syncthing uses one, systemd the other).

```bash
systemctl is-active plaud-sync     # "active" → you are on the service host
```

If not active here, say so plainly — *"run logs live on bg-pc/lark-server"* — rather than
reporting an empty history as a clean bill of health. What still works on any clone: prompt edits,
taxonomy changes, `check-drift.py`, and reading the code.

## Scripts

```bash
python3 .claude/skills/plaud-sync-ops/scripts/runstats.py [--days N] [--json]
python3 .claude/skills/plaud-sync-ops/scripts/check-drift.py [--quiet]
```

**`runstats.py`** — success rate, cost (all / last 10 / window), mean duration, the backlog trend
from the planner's own reports, daily burn, and **the uids that never synced on any attempt**.
Those last ones are the actionable output: each is a recording the watcher consumed without
filing, recoverable only with `/replay-note`.

Always recompute rather than quoting a cost figure from a document. The baseline in `CLAUDE.md`
went stale by 3× before anyone noticed, which is why this script exists. Its cost means exclude
`cost_usd` of 0 — that marks a run whose result envelope never parsed, not a free run.

**`check-drift.py`** — verifies the taxonomy agrees across the four file copies (sync prompt list,
sync prompt glosses, planner weights, commands-prompt count, skill reference table). Exit 1 on
drift. It **cannot** check Notion; finish the job by fetching both data sources and comparing
against the list it prints.

## Traps — each of these has already cost a day

- **The sync prompt is read once at startup.** Editing `plaud-sync-prompt.txt` does nothing until
  `sudo systemctl restart plaud-sync`. But `planner-commands-prompt.txt` is read *per use* — edit
  it freely, no restart. `planner-prompt.txt` is read per run by `planner.py`, also no restart.
- **MCP *write* tools in `.claude/settings.json`'s `ask` list silently break the watcher.** `ask`
  outranks the `--allowedTools` allowlist, and headless `claude -p` has nobody to approve the
  prompt, so the call stalls and the model gives up with a prose apology. Keep Notion and Calendar
  **write** tools out of `ask`. This broke `notion-create-pages` on 2026-07-22.
- **A stalled run still exits 0 with `is_error=false`.** That is why `log_run` gates `ok` on
  `_page_written()` — positive evidence a page landed. Never reintroduce a bare exit-status check.
- **The service must run the venv interpreter**, `/home/robert/plaud-sync/.venv/bin/python`. System
  Python has no `imapclient`. Never "fix" it to `/usr/bin/python3`.
- **The Google Calendar MCP is `claude_ai_Google_Calendar`**, not `google-calendar`. The default
  hardcoded at `plaud_watcher.py:46` is stale; `.env` overrides it correctly. If calendar writes
  stop, check `ALLOWED_TOOLS` in `.env` first.
- **Notion SQL is metered on this workspace**; view mode is not. Prompts read through views.
- **`systemctl start planner@<mode>.service` blocks for minutes** (`Type=oneshot`). Not a hang —
  use `--no-block` or the timers.
- **Auth is inherited, not configured.** Headless runs use `robert`'s interactive login and
  user-scope MCP OAuth. That is why the unit pins `User=robert` and `HOME=/home/robert`. Verify
  with `claude mcp list`.

## Procedures

`reference/procedures.md` — service control, failure triage and replay, editing prompts safely,
adding a Project, and the dev loop for testing a prompt change without spending a real run.

## Related

- `CLAUDE.md` — architecture and the full gotcha list. Still the source of truth.
- `PLANNER-SPEC.md` — the planner's design.
- `SKILLS-SPEC.md` — why these two skills exist and how they are distributed.
- `/sync-health`, `/replay-note`, `/plan-now` — slash commands wrapping the common operations.
