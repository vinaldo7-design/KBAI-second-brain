---
description: Cross-domain analogies for a vault note via analogous-to edges
---

Find cross-domain analogies for a vault note.

1. Call `mcp__mini-vinny__get_note_with_context(note_id="$ARGUMENTS")` to load it.
2. Call `mcp__mini-vinny__graph_expand(note_id="$ARGUMENTS", max_hops=2)`.
3. From the result, filter to edges where `edge_type == "analogous-to"`. Sort by hop ascending then weight descending.
4. Reply with **2–5 analogies**, each one sentence describing the structural parallel and citing the analogue note inline: `(via [[note-id]])`.
5. If fewer than 2 `analogous-to` edges exist, say so and suggest one cross-domain candidate the user might add — name the domain, name the analogue, explain the structural fit in one sentence.

No preamble.
