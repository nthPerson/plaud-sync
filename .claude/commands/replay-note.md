---
description: Re-run the sync for one recording by title or Plaud file ID (use after a failed run)
argument-hint: <recording title, Plaud file ID, or runs.jsonl uid>
---

Replay the sync pipeline for: **$ARGUMENTS**

The watcher marks every email processed whether or not the run succeeded, so failures never retry on
their own. This command performs that retry in-session, using the same prompt the service uses.

Steps:

1. Resolve the target. If the argument is a `uid`, look it up in `runs.jsonl` to recover the subject.
   Strip any `[Plaud-AutoFlow] ` prefix to get the recording title. Find the recording with
   `mcp__plaud__list_files` (use its `query` filter on the title).

2. Check for a page that already exists in the Notion database — data source
   `collection://bbc6c9aa-a96b-4501-a41a-8bd1b5a75866`. If one is already there, say so and stop
   rather than creating a duplicate. Ask me whether to overwrite it.

3. Otherwise follow `plaud-sync-prompt.txt` verbatim against this recording: create the Notion page
   with the exact property options that file specifies, then create calendar events only for
   genuinely dated items, resolving relative dates against the *recording's* date.

4. Before creating any calendar event, search the calendar for a near-duplicate and skip if found.

5. Report what you created — page URL, chosen Area/Type/Project/Tags, and each event. If this replay
   corresponds to a `runs.jsonl` record, tell me which one so I can reconcile.

Read `plaud-sync-prompt.txt` first; it is the source of truth for classification, not this file.
