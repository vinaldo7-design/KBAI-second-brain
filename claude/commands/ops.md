---
description: Operationalise a vault note — concrete how-to steps, biased toward operationalises and exemplifies edges
---

Convert a vault note from theory to practice.

1. Call `mcp__mini-vinny__get_note_with_context(note_id="$ARGUMENTS")` to load it.
2. Call `mcp__mini-vinny__assemble_context(query=<the note's title or summary>, mode="standard", seed_k=5)`.
3. From the result, prefer notes connected via `operationalises` or `exemplifies` edges (visible in `reasoning_path`).
4. Reply with **3–7 concrete steps** — verbs first, no theory restatement. Each step cites the source note inline: `(via [[note-id]])` if it draws on a specific concept.
5. If the note has no operationalises/exemplifies neighbours, say so and propose what kind of worked example would close the gap.

No preamble. Skip background — the user already knows the concept.
