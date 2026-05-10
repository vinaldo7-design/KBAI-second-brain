---
description: Show short, semantic paths between two vault notes
---

Find how two vault notes are conceptually connected. Args: `<note-id-1> <note-id-2>` (space-separated).

## Step 0 — resolve both refs

Parse `$ARGUMENTS` into `raw_from` (first token) and `raw_to` (second token).

For each, call `mcp__mini-vinny__vault_search(query=<raw>, top_k=5)`:
- If top score >= 0.7: resolve to that note_id.
- If 0.4 <= top score < 0.7: print `"<raw>" is ambiguous:` + numbered candidates. Ask user to pick before proceeding. Stop.
- If top score < 0.4 AND the raw token isn't an exact note_id: print `No match for "<raw>".` Stop.

Print one line: `From: [[<from_id>]]  →  To: [[<to_id>]]` before proceeding.

## Step 1 — load start note

Call `mcp__mini-vinny__get_note_with_context(note_id=<from_id>)` to grab the title.

## Step 2 — path retrieval

Call `mcp__mini-vinny__assemble_context(query=<from note's title>, mode="standard", seed_k=3)`.

Look for `<to_id>` in the returned notes. If present, surface its `reasoning_path` directly — that's the answer.

If `<to_id>` is not in the top 50 PPR results: call `mcp__mini-vinny__graph_expand(note_id=<from_id>, max_hops=3)` and check whether `<to_id>` appears. If yes, reconstruct the chain manually from the hop data; if no, report that no semantic path exists within 3 hops and suggest the missing edge that would connect them.

## Step 3 — reply

Each step on its own line: `[[from]] --(edge-type)--> [[to]]`

Then one sentence describing what the path means conceptually.

No preamble.
