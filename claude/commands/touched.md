---
description: Show the 20 most recently modified notes that mention a topic (filename substring match).
---

Topic: `$ARGUMENTS`

## Step 1 — fetch

Call `mcp__mini-vinny__recent_notes(limit=20, topic="$ARGUMENTS")`.

## Step 2 — render

If the list is empty: print `No notes matching "$ARGUMENTS" found.`

Otherwise print a compact table:

```
note_id                        modified
-----------------------------  --------
<note_id>                      2d ago
```

Use relative timestamps (same as /recent: Xm/Xh/Xd ago, or ISO date beyond 7 days).

No preamble.
