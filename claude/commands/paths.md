---
description: Show short, semantic paths between two vault notes
---

Find how two vault notes are conceptually connected. Args: `<note-id-1> <note-id-2>` (space-separated).

1. Parse $ARGUMENTS into two note ids: `from_id` and `to_id`.
2. Call `mcp__mini-vinny__get_note_with_context(note_id=<from_id>)` to grab the title.
3. Call `mcp__mini-vinny__assemble_context(query=<from note's title>, mode="standard", seed_k=3)`.
4. Look for `to_id` in the returned notes. If present, surface its `reasoning_path` directly — that's the answer.
5. If `to_id` is not in the top 50 PPR results: call `mcp__mini-vinny__graph_expand(note_id=<from_id>, max_hops=3)` and check whether `to_id` appears. If yes, reconstruct the chain manually from the hop data; if no, report that no semantic path exists within 3 hops and suggest the missing edge that would connect them.
6. Reply format: each step on its own line as `[[from]] --(edge-type)--> [[to]]`. Then one sentence describing what the path means conceptually.

No preamble.
