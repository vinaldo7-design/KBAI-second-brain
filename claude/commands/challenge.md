---
description: Sparring mode — surface contradicts/challenges edges to pressure-test a vault note
---

Pressure-test a vault note using its dialectical opponents.

1. Call `mcp__mini-vinny__get_note_with_context(note_id="$ARGUMENTS")` to load it.
2. Call `mcp__mini-vinny__assemble_context(query=<the note's title or summary>, mode="sparring", seed_k=5)` — `mode="sparring"` is required, otherwise contradicts edges are excluded from the PPR walk and you'll get nothing useful.
3. Filter the results: prioritise notes connected via `contradicts` or `challenges` edges (visible in `reasoning_path`).
4. Reply with **3–7 sparring points**, each one sentence, citing the opposing note inline: `(via [[note-id]])`.
5. End with one line: which sparring point is the strongest objection and why.

No preamble. If no contradicts/challenges edges exist for this note, say so directly and suggest running `/audit-edges` to find force-fit edges that could be retyped.
