---
description: Show all vault notes modified today (since midnight local time).
---

## Step 1 — compute midnight timestamp

Compute the Unix timestamp for today's midnight (local time, not UTC). Use Python semantics:
```python
import time
today = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
```

## Step 2 — fetch

Call `mcp__mini-vinny__recent_notes(limit=50, since_ts=<midnight_ts>)`.

## Step 3 — render

If the list is empty: print `Nothing touched today.`

Otherwise print a compact table (same "Xh ago" format as /recent):

```
note_id                        modified
-----------------------------  --------
<note_id>                      3h ago
```

No preamble.
