---
description: Cross-domain analogies for a vault note via analogous-to edges
---

Find cross-domain analogies for a vault note.

## Step 0 — resolve note ref

Call `mcp__mini-vinny__vault_search(query="$ARGUMENTS", top_k=5)`.

- If top score >= 0.7: resolve to that note_id, print `Resolved: [[<note_id>]] (score <confidence>)`, continue.
- If 0.4 <= top score < 0.7: print candidates and ask user to pick. Stop.
- If top score < 0.4: print `No matching note found for "$ARGUMENTS".` Stop.

## Step 1 — load

Call `mcp__mini-vinny__get_note_with_context(note_id=<resolved_id>)`.

## Step 2 — expand

Call `mcp__mini-vinny__graph_expand(note_id=<resolved_id>, max_hops=2)`.

## Step 3 — reply

From the result, filter to edges where `edge_type == "analogous-to"`. Sort by hop ascending then weight descending.

Reply with **2–5 analogies**, each one sentence describing the structural parallel and citing the analogue note inline: `(via [[note-id]])`.

If fewer than 2 `analogous-to` edges exist, say so and suggest one cross-domain candidate the user might add — name the domain, name the analogue, explain the structural fit in one sentence.

No preamble.
