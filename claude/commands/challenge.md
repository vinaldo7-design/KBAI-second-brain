---
description: Sparring mode — surface contradicts/challenges edges to pressure-test a vault note
---

Pressure-test a vault note using its dialectical opponents.

## Step 0 — resolve note ref

Call `mcp__mini-vinny__vault_search(query="$ARGUMENTS", top_k=5)`.

- If top score >= 0.7: resolve to that note_id, print `Resolved: [[<note_id>]] (score <confidence>)`, continue.
- If 0.4 <= top score < 0.7: print candidates and ask user to pick. Stop.
- If top score < 0.4: print `No matching note found for "$ARGUMENTS".` Stop.

## Step 1 — load

Call `mcp__mini-vinny__get_note_with_context(note_id=<resolved_id>)`.

## Step 2 — sparring retrieval

Call `mcp__mini-vinny__assemble_context(query=<the note's title or summary>, mode="sparring", seed_k=5)` — `mode="sparring"` is required, otherwise contradicts edges are excluded from the PPR walk and you'll get nothing useful.

## Step 3 — reply

Filter the results: prioritise notes connected via `contradicts` or `challenges` edges (visible in `reasoning_path`).

Reply with **3–7 sparring points**, each one sentence, citing the opposing note inline: `(via [[note-id]])`.

End with one line: which sparring point is the strongest objection and why.

No preamble. If no contradicts/challenges edges exist for this note, say so directly and suggest running `/audit-edges` to find force-fit edges that could be retyped.
