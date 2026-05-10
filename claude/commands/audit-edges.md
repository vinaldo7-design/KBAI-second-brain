---
description: Run audit_taxonomy on two edge types, present top retype candidates
---

Audit edges of one type for semantic drift toward another. Args: `<check-type> <against-type>` (space-separated, must both exist in vault_taxonomy.yaml).

Valid types: `builds-on`, `builds-toward`, `contradicts`, `analogous-to`, `exemplifies`, `challenges`, `operationalises`, `referenced-in`, `untyped`, `mentioned`.

1. Parse $ARGUMENTS into `check_type` and `against_type`.
2. Call `mcp__mini-vinny__audit_taxonomy(check_type=<check_type>, against_type=<against_type>)`.
3. Reply with the **top 10 results** as a tight table:
   ```
   #  Score  Source → Target                              Suggested
   1  0.62   note-a → note-b                              retype to <against>
   2  0.58   ...                                          keep
   ```
   "Suggested" = `retype to <against>` if score > 0.55, else `keep`.
4. End with one line: *"N candidates above 0.55 — apply retypes? (y/n)"*. If yes, list the specific edges that would change; do not patch automatically (retyping needs `mcp__mcp-obsidian__obsidian_patch_content` with user confirmation per edge).

No preamble. If either type is invalid, return the error from `audit_taxonomy` directly.
