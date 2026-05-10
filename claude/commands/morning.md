---
description: Morning briefing — 5 recent notes with summaries + a council question suggestion. Experimental.
---

## Step 1 — recent surface

Call `mcp__mini-vinny__recent_notes(limit=5)`.

## Step 2 — enrich

For each note in the list call `mcp__mini-vinny__get_note_with_context(note_id=<note_id>)`.
Extract the first non-empty `summary` field or the first sentence of `content`. Cap at 80 chars.

## Step 3 — council suggestion

Pick the note from the recent list that looks most like an open question or decision point (look for interrogative language, "should", "trade-off", "vs", "tension").
If none obvious, pick the most recently modified.

Print:
```
## Today's surface

note_id                        | summary
-------------------------------|----------------------------------------------------
<note_id>                      | <≤80 char summary>
...

## Council suggestion

Try: /council <chosen_note_id>
```

No preamble. This is a read-only morning orientation — no writes, no research calls.
