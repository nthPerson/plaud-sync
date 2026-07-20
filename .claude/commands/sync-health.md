---
description: Report watcher health — service state, recent runs, cost trend, and any failures needing replay
---

Report on the health of the plaud-sync automation. Be concise — this is a status check, not an audit.

1. Service state: `systemctl status plaud-sync --no-pager | head -12`
2. Recent errors: `grep -iE 'error|timeout|exited' plaud-sync.log | tail -15`
3. Run history from `runs.jsonl` — for each record print time, ok, cost, duration, subject.
   Then report: total runs, success rate, mean/median cost, mean duration, and total spend.
4. Drift check: `diff plaud-sync.service /etc/systemd/system/plaud-sync.service`
5. MCP reachability: `claude mcp list`

Then give me:
- A one-line verdict (healthy / degraded / down).
- Any UIDs in `runs.jsonl` with `ok: false` — these were consumed without syncing and need manual
  replay. Name them explicitly.
- Whether cost per run is trending up versus the ~$0.59 baseline recorded in CLAUDE.md.

Do not restart the service or change any state.
