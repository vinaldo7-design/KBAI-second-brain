---
description: Read-only vault health audit. Triggers on "audit the vault", "check link health", "find missing connections", "audit edges". Two modes: links (connect-suggest, 5 categories of missing links) and edges (taxonomy drift between two edge types). No writes — preview only. Use when the user wants to see graph quality issues, not fix them automatically.
---

Arguments: `$ARGUMENTS`

## Dispatch by arg shape

| Pattern | Mode |
|---|---|
| empty | **links** — full connect-suggest run (all 5 categories) |
| `links` | **links** — same as empty |
| `edges <type1> <type2>` | **edges** — taxonomy drift between two edge types |

## Mode: links (default)

Call `mcp__mini-vinny__analytics_connect_suggest()`.

For each category with candidates, render:
```
### <category_name>
1. [[note_a]] → [[note_b]]  (<edge_type>): <rationale>
2. ...
```

Order: missing_bidir → analogous_cross_domain → implicit_contradicts → orphan_rescue → low_centrality_high_substance.
Skip empty categories.

End with:
```
To apply: tell me which numbers to add (e.g. "add 1, 3, 7").
No links will be added without explicit confirmation.
```

## Mode: edges

Parse `<type1>` and `<type2>` from args. Valid types: `builds-on`, `builds-toward`, `contradicts`, `analogous-to`, `exemplifies`, `challenges`, `operationalises`, `referenced-in`, `untyped`, `mentioned`.

Call `mcp__mini-vinny__audit_taxonomy(check_type=<type1>, against_type=<type2>)`.

Render top 10 as a tight table:
```
#  Score  Source → Target                            Suggested
1  0.62   note-a → note-b                            retype to <type2>
```
"Suggested" = `retype to <type2>` if score > 0.55, else `keep`.

End: *"N candidates above 0.55 — apply retypes? (y/n)"*. Do not patch automatically.

No preamble. Errors returned directly.
