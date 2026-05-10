---
description: Explain a vault note using semantic + graph retrieval (builds-on, exemplifies, operationalises bias)
---

You're explaining a vault note from Mini Vinny.

1. Call `mcp__mini-vinny__get_note_with_context(note_id="$ARGUMENTS")` to load the note's title, summary, and edges.
2. Call `mcp__mini-vinny__assemble_context(query=<the note's title or summary>, mode="standard", seed_k=5)`.
3. From the result, prefer notes whose `reasoning_path` traverses `builds-on`, `exemplifies`, or `operationalises` edges.
4. Reply with **3–5 bullets** explaining the note's core argument and how it connects to the rest of the vault. Cite each claim inline at the bullet level: `(via [[note-id]])` — never a trailing References section.
5. Cap at ~250 words. No preamble, no recap.

If the note id is unknown, return the error from `get_note_with_context` directly — don't guess.
