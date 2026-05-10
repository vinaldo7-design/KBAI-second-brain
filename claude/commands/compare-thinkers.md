---
description: Compare two or more cognitive profiles on the same query — side-by-side top-10 table, divergence score, 3-sentence synthesis.
---

Arguments: `$ARGUMENTS`

Parse the arguments: the first token is a `+`-joined profile spec (e.g. `explorer+skeptic` or `operator+builder+skeptic`). Everything after the first space is the query.

## Step 1 — retrieve

Call `mcp__mini-vinny__cognition_compare_profiles(query=<query>, profile_ids=[<profiles split on +>], top_k=10)`.

## Step 2 — render

Print a compact side-by-side table:

```
Rank | <profile_1>          | <profile_2>          | ...
-----|----------------------|----------------------|----
 1   | note-id (score)      | note-id (score)      | ...
 2   | ...                  | ...                  | ...
...
10   | ...                  | ...                  | ...
```

Then print: `Divergence score: <divergence_score>  (0.0 = identical · 1.0 = disjoint)`

## Step 3 — synthesis (exactly 3 sentences)

1. **Consensus**: What do the profiles agree on? Name the shared notes and what that agreement signals about the query.
2. **Divergence**: Where do they split? Name the profile-unique notes and what each lens is pulling toward that the others aren't.
3. **Observation**: Is the divergence meaningful (different genuine perspectives on the question) or noise (minor score re-ranking of essentially the same set)? Name which profile surfaced something you wouldn't have found with the default lens, if any.

No preamble. No trailing notes. Table first, score line, then exactly three sentences.
