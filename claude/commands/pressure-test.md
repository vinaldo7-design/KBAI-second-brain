---
description: Full pressure test — sparring retrieval, strongest counterarguments, optional council if contradictions found.
---

Arguments: `$ARGUMENTS`

## Step 0 — resolve

Call `mcp__mini-vinny__vault_search(query="$ARGUMENTS", top_k=5)`.

If the top result has score >= 0.7, use its `note_id` as the target. Otherwise treat `$ARGUMENTS` as the query directly.

## Step 1 — challenge

Call `mcp__mini-vinny__assemble_context(query=<target>, mode="sparring", seed_k=5)`.

Surface the 3 strongest counterarguments from the result. For each:
- State the challenge in one sentence
- Cite the source note inline: `(via [[note_id]])`

## Step 2 — council escalation (conditional)

If any retrieved note has edge type `contradicts` or `challenges`: call `mcp__mini-vinny__council_retrieve(query=<target>, top_k=10)`.
Synthesize: one sentence per lens that disagrees, then one "verdict" sentence on whether the contradictions are fatal or resolvable.

If no contradicts/challenges edges found: skip Step 2.

## Step 3 — edit suggestions

List up to 3 specific edits that would make the target note more defensible:
- One for each major vulnerability surfaced in Step 1/2

Format: `- [ ] <edit suggestion>` (as a checklist, so user can copy to note)

No preamble.
