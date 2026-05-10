---
description: Suggest missing links in the vault — 5 categories, preview only, no writes.
---

## Step 1 — analyse

Call `mcp__mini-vinny__analytics_connect_suggest()`.

## Step 2 — render

For each category that has candidates, print a section:

```
### <category_name>
1. [[note_a]] → [[note_b]]  (<edge_type>): <rationale>
2. ...
```

Categories (in order):
1. `missing_bidir` — edges that exist one-way but not the other
2. `analogous_cross_domain` — analogous-to links across domain boundaries
3. `implicit_contradicts` — implicit contradictions not yet labelled
4. `orphan_rescue` — isolated notes with strong semantic neighbours
5. `low_centrality_high_substance` — high-value notes with few links

Skip any category with zero candidates.

## Step 3 — instruction

Print:
```
To apply: tell me which numbers to add (e.g. "add 1, 3, 7").
No links will be added without explicit confirmation.
```

No preamble.
