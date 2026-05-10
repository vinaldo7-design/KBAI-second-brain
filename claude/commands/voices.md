---
description: List all available voices in ~/.claude/voices/ with their descriptions and combination hints
---

List the voice library.

1. Read every `.md` file in `~/.claude/voices/` (skip `README.md`).
2. For each, extract the frontmatter: `voice`, `description`, `dimensions`, `combines_well_with`, `combines_poorly_with`.
3. Present as a compact table:

```
Voice       Description                                      Dimensions
─────────────────────────────────────────────────────────────────────────
naval       Short aphoristic compression                     length:short structure:aphoristic register:casual-sharp
tharoor     Long argumentative erudite prose                 length:long structure:argumentative register:erudite
...
```

Then list combination hints:
- "naval + bourdain" — usually strong (compression + observation)
- "tharoor + clarkson" — risky, asks for restraint to land

End with: *"Invoke with `/voice <name> <query>` or `/voice <a>+<b> <query>`."*

No preamble.
