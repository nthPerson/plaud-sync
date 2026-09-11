# Procedures

Service host is **bg-pc / lark-server**. Check with `systemctl is-active plaud-sync` before
anything in the first two sections.

## Service control

```bash
systemctl status plaud-sync
journalctl -u plaud-sync -f              # live
tail -f plaud-sync.log
sudo systemctl restart plaud-sync        # after editing plaud_watcher.py or .env or the SYNC prompt

systemctl list-timers 'planner@*' plaud-digest.timer
sudo systemctl start planner@morning.service --no-block    # blocks for minutes without --no-block
```

Foreground run (stop the service first, or it double-processes):

```bash
sudo systemctl stop plaud-sync
set -a; source .env; set +a; .venv/bin/python plaud_watcher.py
```

Unit drift check: `diff plaud-sync.service /etc/systemd/system/plaud-sync.service`. They should be
byte-identical; reinstall with
`sudo cp plaud-sync.service /etc/systemd/system/ && sudo systemctl daemon-reload`.

## Failure triage

1. `runstats.py` — it names the uids that never synced on any attempt.
2. For each, find the record: `grep '"uid": <n>' runs.jsonl | python3 -m json.tool`.
3. Read the `error` and `summary` fields. The three failure modes seen so far:

| Symptom | Cause | Fix |
|---|---|---|
| `timeout after 600s` | long transcript, slow MCP | raise `CLAUDE_TIMEOUT`, or replay when quieter |
| `MCP servers blocked by enterprise policy` | a connector was disabled | re-check `claude mcp list`, then replay |
| `see summary`, prose apology, no page | a write tool stalled on an `ask` gate | fix `settings.json`, then replay |

4. Replay with `/replay-note <title or file id>`. The watcher marks every email processed whether
   or not the run succeeded, so **failures never retry themselves** beyond the one automatic retry.

Manual replay without the slash command: drop the uid from `processed.json`, mark the email unread
in Gmail, restart the service.

## Editing prompts

| File | Read when | Restart needed |
|---|---|---|
| `plaud-sync-prompt.txt` | watcher startup | **yes** |
| `planner-commands-prompt.txt` | per command | no |
| `planner-prompt.txt` | per planner run | no |
| `weekly-digest-prompt.txt` | per digest run | no |

Test a sync-prompt change **without** touching email or waiting for a recording:

```bash
claude -p "$(cat plaud-sync-prompt.txt)

---
## The recording to process
- Email subject: <subject>
- Plaud link found in email: none found — locate by title + recency
- Email received (UTC): $(date -u +%FT%TZ)" \
  --model sonnet \
  --allowedTools 'mcp__plaud__*,mcp__notion__*,mcp__claude_ai_Google_Calendar__*' \
  --output-format json
```

This is the main dev loop. Step 2's create-or-update idempotency (keyed on `Source Link`) makes it
safe to run repeatedly against the same recording.

## Adding a Project

Five places. Missing one fails **silently** — the automation writes a value the schema lacks, or
scores a project it has never heard of.

1. `Project` select on the Tasks data source (`collection://be0b1624-…`)
2. `Project` select on the Plaud Notes data source (`collection://bbc6c9aa-…`)
3. `plaud-sync-prompt.txt` — the option list **and** a `->` gloss **and** any tie-breaker
4. `planner-prompt.txt` — a weight in the Step 4 scoring table
5. `skills/plaud-sync-planner/reference/notes.md` — the project table

Plus: `planner-commands-prompt.txt`'s "one of the N options" count if the Tasks DB total changed,
`CLAUDE.md`'s list, and a dashboard or linked view — otherwise the project's notes surface nowhere.

**The select edit is the dangerous step.** `ALTER COLUMN "Project" SET SELECT(...)` **replaces**
the entire option list, so re-list every existing option *with its colour*, then re-fetch to
confirm nothing was dropped. The two databases use different colours for the same project;
preserve each one's. Options that exist only on the Notes DB (`Planner`) must not be added to
Tasks.

Finish with `check-drift.py`, then the two `notion-fetch` calls it prints.

Retiring a project at term end: remove it from the prompts, but **leave the Notion option in
place** or historical rows lose their value.

## Cost work

`runstats.py --days 30` for the trend. Levers, cheapest first:

- `PLANNER_MODEL=haiku` for command runs (they are simple and already the cheapest at ~$0.52).
- Smaller `canvas.days_ahead` in `planner-sources.json`.
- **Task-84**: migrate the three prompts from reading the whole `Open` view to `rows` mode with
  server-side filters. This is the dominant input in every run and the biggest lever left.
- Batching commands into the next planner run instead of applying immediately (a one-line change
  in the watcher) — but it costs the immediacy Robert chose deliberately.

## Secrets

`.env` holds the Gmail app password and `CANVAS_TOKEN`; it is git-ignored and `Read`-denied in
`.claude/settings.json`. Never print it, never copy it to another machine, never put the repo in a
synced folder (`SKILLS-SPEC.md` §6).
