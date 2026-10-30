---
description: Find notes. Triggers on "find X", "search the vault for X", "what's recent", "what did I touch today", "recent notes on X". Searches by meaning, or lists recently modified notes.
---

Arguments: `$ARGUMENTS`

## Dispatch by arg shape

| Pattern | Call |
|---|---|
| `recent` or `recent <N>` | `mcp__mini-vinny__recent_notes(limit=N)`, default 10 |
| `today` | `mcp__mini-vinny__recent_notes(limit=50, since_ts=<local midnight as a Unix timestamp>)` |
| `touched <topic>` | `mcp__mini-vinny__recent_notes(limit=20, topic=<topic>)` |
| anything else | `mcp__mini-vinny__retrieve_search(query="$ARGUMENTS", top_k=5)` |

## Search results

Print a compact table. `score` is a distance, so lower is closer:

```
#  | note_id                      | score | title
---|------------------------------|-------|------
1  | <note_id>                    | 0.62  | <title>
2  | ...
```

Then print one line: `Pick a number to open, or type a note_id directly.` Do not open any note automatically. Wait for the user's selection.

## Recent results

If the list is empty, say so in one line. Otherwise print a compact table with relative times from `modified_ts`: `just now`, `Xm ago`, `Xh ago`, `Xd ago`, or an ISO date beyond 7 days.

```
note_id                        modified
-----------------------------  --------
<note_id>                      2h ago
```

No preamble.
