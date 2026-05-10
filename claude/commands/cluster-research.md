---
description: Research a whole map cluster with Perplexity — 14-day cost guard, then apply findings to the map note.
---

Arguments: `$ARGUMENTS`

Parse `map_id` from the first token. Optional second token: `hops=N` (default 1).

## Step 0 — resolve map

Call `mcp__mini-vinny__vault_search(query="$ARGUMENTS", top_k=3)`.

If top result score >= 0.7 and the note_id looks like a map (contains "map", "index", "moc", or lives in `06-Maps/`), use it. Otherwise use the first token literally as `map_id`.

## Step 1 — 14-day cost guard

Query the Perplexity research log:
```sql
SELECT research_ts FROM research_log
WHERE note_id = '<map_id>'
ORDER BY research_ts DESC LIMIT 1
```

If researched within 14 days, print:
```
Last researched: <date>. Re-run with /cluster-research <map_id> --force to override.
```
And stop unless `--force` was in `$ARGUMENTS`.

## Step 2 — research

Call `mcp__perplexity-research__research_cluster(map_id=<map_id>, cluster_hops=<hops>)`.

## Step 3 — summary

Print:
```
Cluster: <map_id>  (<N> notes researched)

Key findings:
- <finding 1>
- <finding 2>
...

Cross-links suggested:
- [[note_a]] ↔ [[note_b]]: <reason>
...
```

## Step 4 — apply (confirm first)

Ask: `Apply these findings to [[<map_id>]]? (y/n)`

On `y`: call `mcp__perplexity-research__apply_research(note_id=<map_id>, ...)` with the full result from Step 2.
On `n`: print `Findings not applied. You can apply manually.`
