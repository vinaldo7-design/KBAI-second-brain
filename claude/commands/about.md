---
description: Explain a vault note using semantic + graph retrieval (builds-on, exemplifies, operationalises bias)
---

You're explaining a vault note from Mini Vinny.

## Step 0 — resolve note ref

Call `mcp__mini-vinny__vault_search(query="$ARGUMENTS", top_k=5)`.

- If `$ARGUMENTS` is an exact note_id (kebab-case, no spaces) AND `get_note_with_context` returns a valid note: proceed with that id.
- If top search score >= 0.7: use that note_id, print one line `Resolved: [[<note_id>]] (score <confidence>)`, continue.
- If 0.4 <= top score < 0.7: print a numbered list of candidates and ask the user to pick one. Stop.
- If top score < 0.4 or no results: print `No matching note found for "$ARGUMENTS".` Stop.

## Step 1 — load

Call `mcp__mini-vinny__get_note_with_context(note_id=<resolved_id>)`.

## Step 2 — context

Call `mcp__mini-vinny__assemble_context(query=<the note's title or summary>, mode="standard", seed_k=5)`.

## Step 3 — reply

From the result, prefer notes whose `reasoning_path` traverses `builds-on`, `exemplifies`, or `operationalises` edges.

Reply with **3–5 bullets** explaining the note's core argument and how it connects to the rest of the vault. Cite each claim inline at the bullet level: `(via [[note-id]])` — never a trailing References section.

Cap at ~250 words. No preamble, no recap.
