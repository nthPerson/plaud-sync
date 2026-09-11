# Plaud — the recording device

Available as an MCP in Claude Code and as a connector in the Claude Desktop app (authenticated
2026-09-11). Five tools, the same on both: `list_files`, `get_file`, `get_note`, `get_transcript`,
`get_current_user`.

## Do not use it for recall

**The full transcript is already in the Notion note page.** `get_file` returns the entire
transcript unconditionally — there is no way to ask for just the summary — so using Plaud to answer
"what did Reza ask for?" pulls a whole recording into context to find one sentence. Search the
Notes DB instead; it returns the page.

This is a context-economy rule, not an availability one. The tools work fine. They are just the
expensive way to answer a question Notion already answers.

## The one-call rule

When you *do* need the source, **one `get_file` gets everything**:

- the AI summary — `note_list`, data_type `auto_sum_note`
- the topic outline — `source_list`, data_type `outline`
- the full speaker-labelled transcript — `source_list`, data_type `transaction`

`get_note` and `get_transcript` are strict subsets of that payload. Calling them in addition is
pure waste.

Plaud's **mind map is not exposed by the MCP at all** — no mindmap entry appears in any recording's
`note_list`. The sync synthesises a Mermaid equivalent instead. Do not go looking for an API that
provides one.

## Finding a recording

```
list_files(query=<distinctive title words>, date_from=YYYY-MM-DD, date_to=YYYY-MM-DD)
```

Both filters together, aiming at a single result. `query` is a case-insensitive substring of the
title. Emails from Plaud arrive within minutes of the recording, so the recording date and the
notification date match.

The durable identifier is the recording **`id`**, never the title. It reconstructs the web URL:

```
https://web.plaud.ai/file/<id>
```

which is exactly what the Notion `Source Link` holds, on both the note page and any task extracted
from it. That link is the join key in both directions.

## What the connector is actually for: reconciliation

Everything upstream of Notion. The sync marks each notification email processed whether or not the
run succeeded, so a failed run leaves a recording with **no Notion page and no further signal** —
13 runs failed that way between 2026-07-23 and 2026-08-18, each discoverable only from a failure
email. Recipe **R15** in `recipes.md` compares `list_files` against the Notes DB by `Source Link`
and reports the gaps.

## What not to do from a conversation

**Do not file a recording into Notion by hand.** Doing it properly needs the sync prompt's full
classification taxonomy, and reproducing that here would create a second copy that drifts from the
original. Detect the gap and report it; the watcher or `/replay-note` in the repo fills it.
