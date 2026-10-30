---
description: Pressure-test a vault note. Triggers on "challenge X", "what's wrong with X", "pressure test X". Surfaces contradicts and challenges edges, and takes it to the council when real contradictions turn up.
---

Pressure-test a vault note using its dialectical opponents.

## Step 0 — resolve note ref

Call `mcp__mini-vinny__retrieve_search(query="$ARGUMENTS", top_k=5)`.

- If top score >= 0.7: resolve to that note_id, print `Resolved: [[<note_id>]] (score <confidence>)`, continue.
- If 0.4 <= top score < 0.7: print candidates and ask user to pick. Stop.
- If top score < 0.4: print `No matching note found for "$ARGUMENTS".` Stop.

## Step 1 — load

Call `mcp__mini-vinny__notes_get_with_context(note_id=<resolved_id>)`.

## Step 2 — sparring retrieval

Call `mcp__mini-vinny__retrieve_assemble(query=<the note's title or summary>, mode="sparring", seed_k=5)` — `mode="sparring"` is required, otherwise contradicts edges are excluded from the PPR walk and you'll get nothing useful.

## Step 3 — reply

Filter the results: prioritise notes connected via `contradicts` or `challenges` edges (visible in `reasoning_path`).

Reply with **3–7 sparring points**, each one sentence, citing the opposing note inline: `(via [[note-id]])`.

End with one line: which sparring point is the strongest objection and why.

## Step 4 — council, only if contradictions turned up

If any retrieved note is connected by `contradicts` or `challenges`, call `mcp__mini-vinny__council_retrieve(query=<the note's title>, top_k=10)`. Add one sentence per lens that disagrees, then one sentence on whether the contradictions are fatal or resolvable.

Then list up to 3 edits that would make the note more defensible, as a checklist: `- [ ] <edit>`.

No preamble. If no contradicts/challenges edges exist for this note, say so directly and suggest running `/audit edges <type1> <type2>` to find force-fit edges that could be retyped.
