---
description: Search the vault for notes matching a query — returns a compact ranked table, then waits for you to pick one.
---

Query: `$ARGUMENTS`

## Step 1 — search

Call `mcp__mini-vinny__vault_search(query="$ARGUMENTS", top_k=5)`.

## Step 2 — render

Print a compact table:

```
#  | note_id                      | score | title
---|------------------------------|-------|------
1  | <note_id>                    | 0.87  | <title>
2  | ...
```

## Step 3 — wait

Print one line: `Pick a number to open, or type a note_id directly.`

Do not open any note automatically. Wait for the user's selection.
