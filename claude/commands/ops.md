---
description: Operationalise a vault note — concrete how-to steps, biased toward operationalises and exemplifies edges
---

Convert a vault note from theory to practice.

## Step 0 — resolve note ref

Call `mcp__mini-vinny__vault_search(query="$ARGUMENTS", top_k=5)`.

- If top score >= 0.7: resolve to that note_id, print `Resolved: [[<note_id>]] (score <confidence>)`, continue.
- If 0.4 <= top score < 0.7: print candidates and ask user to pick. Stop.
- If top score < 0.4: print `No matching note found for "$ARGUMENTS".` Stop.

## Step 1 — load

Call `mcp__mini-vinny__get_note_with_context(note_id=<resolved_id>)`.

## Step 2 — context

Call `mcp__mini-vinny__assemble_context(query=<the note's title or summary>, mode="standard", seed_k=5)`.

## Step 3 — reply

From the result, prefer notes connected via `operationalises` or `exemplifies` edges (visible in `reasoning_path`).

Reply with **3–7 concrete steps** — verbs first, no theory restatement. Each step cites the source note inline: `(via [[note-id]])` if it draws on a specific concept.

If the note has no operationalises/exemplifies neighbours, say so and propose what kind of worked example would close the gap.

No preamble. Skip background — the user already knows the concept.
