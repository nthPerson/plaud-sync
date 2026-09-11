---
description: Report watcher health — service state, recent runs, cost trend, and any failures needing replay
---

Report on the health of the plaud-sync automation. Be concise — this is a status check, not an audit.

1. Stats, cost and backlog trend — one command, no ad-hoc python:

   ```
   python3 .claude/skills/plaud-sync-ops/scripts/runstats.py --days 7
   ```

   If it reports no run logs, you are not on the service host (bg-pc / lark-server). Say so and
   stop — an empty history is not a clean bill of health.

2. Service state: `systemctl status plaud-sync --no-pager | head -12`
3. Recent errors: `grep -iE 'error|timeout|exited' plaud-sync.log | tail -15`
4. Drift check: `diff plaud-sync.service /etc/systemd/system/plaud-sync.service`
5. MCP reachability: `claude mcp list`

Then give me:

- A one-line verdict (healthy / degraded / down).
- **The uids `runstats.py` lists as never synced** — recordings consumed without filing, which need
  `/replay-note`. Name them explicitly; nothing else will surface them.
- Whether cost per run is moving. Compare the script's *last 10* against its *all-time* mean rather
  than against any figure written in a document — the baseline in `CLAUDE.md` is a dated snapshot,
  and the previous one drifted 3× before anyone noticed.
- Whether the backlog is growing: the script prints open/overdue per planner run. A rising open
  count with flat completions is the known failure mode, and it is a `/plan-now` or grooming
  problem, not a service problem.

Do not restart the service or change any state.

See `.claude/skills/plaud-sync-ops/` for the full runbook.
