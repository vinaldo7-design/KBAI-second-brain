---
description: Show the N most recently modified vault notes with relative timestamps.
---

Arguments: `$ARGUMENTS`

Parse N from the arguments (default 10 if blank or not a number).

## Step 1 — fetch

Call `mcp__mini-vinny__recent_notes(limit=N)`.

## Step 2 — render

For each note compute a human relative timestamp from `modified_ts`:
- < 60 s → "just now"
- < 3600 s → "Xm ago"
- < 86400 s → "Xh ago"
- < 604800 s → "Xd ago"
- otherwise → ISO date (YYYY-MM-DD)

Print a compact table:

```
note_id                        modified
-----------------------------  ----------
<note_id>                      2h ago
<note_id>                      yesterday
```

No preamble. No trailing commentary.
