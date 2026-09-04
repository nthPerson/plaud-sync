---
description: Run the planner now (Canvas + forwarded email + calendar → Notion Today page + email brief)
argument-hint: [morning|evening|now] [--dry-run] [--no-email]
---

Run the planner in the foreground with the arguments **$ARGUMENTS** (default mode: `now`):

```
set -a; source .env; set +a; .venv/bin/python planner.py --mode ${1:-now} ${@:2}
```

`--dry-run` only prints the bundle Claude would receive (Canvas items, filtered email, recent
commands) and touches nothing — use it to check sources. Without it the run rewrites the Notion
Today page and emails the brief to NOTIFY_EMAIL+planner.

Afterwards report: the last record in `planner-runs.jsonl` (ok, cost, counts), the Today page URL
(https://app.notion.com/p/3d1eb30651108180942dff91930bdd10), and anything the run flagged as
unresolved or failed. Do not restart any service.
