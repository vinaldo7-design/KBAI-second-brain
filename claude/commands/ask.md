---
description: Deterministic intent router — classify the query and call the right tool sequence directly. No slash-command nesting.
---

The query is: `$ARGUMENTS`

## Step 1 — classify intent

Apply these rules in order (first match wins):

| Pattern | Intent |
|---|---|
| "explain X" / "what is X" / bare note-id format (kebab-case, no spaces) | **about** |
| "challenge X" / "what's wrong with X" / "pressure test X" | **challenge** |
| "how do I X" / "operationalize X" / "make X concrete" | **ops** |
| "council X" / "what should I do about X" / ambiguous trade-off | **council** |
| "deep audit X" / "exhaustive search X" / "include mentioned" | **exhaustive** |
| "research X" where X matches note-id format | **research** |
| "compare X" / "X vs Y" / profile1+profile2 in query | **compare** |
| "paths from A to B" / "connect A B" | **paths** |
| anything else | **about** (default) |

Print one line: `routed as intent: <intent>`

## Step 2 — execute

**about**: Call `mcp__mini-vinny__get_note_with_context(note_id=X)` then `mcp__mini-vinny__assemble_context(query=<title or X>, mode="standard")`. Reply with 3–5 bullets citing vault links inline.

**challenge**: Call `mcp__mini-vinny__assemble_context(query=X, mode="sparring", seed_k=5)`. Lead with the strongest counterargument from the result. Cite 2–3 contradicts/challenges notes.

**ops**: Call `mcp__mini-vinny__assemble_context(query=X, mode="standard")`. Surface only `operationalises` and `exemplifies` neighbours. Reply as a numbered how-to list (max 7 steps).

**council**: Call `mcp__mini-vinny__council_retrieve(query=X, top_k=10)`. Synthesize per the /council rules: one paragraph per lens, one synthesis paragraph, one Skeptic note mandatory.

**exhaustive**: Call `mcp__mini-vinny__cognition_retrieve_as(query=X, profile_id="exhaustive", top_k=15)`. Flag any low-signal (mentioned-only) notes explicitly.

**research**: Call `mcp__perplexity-research__research_note(note_id=X)`. Present sources, claim checks, open questions. Do not write to the note unless asked.

**compare**: Parse profile spec (split on `+`), extract query remainder. Call `mcp__mini-vinny__cognition_compare_profiles(query=<query>, profile_ids=[...], top_k=10)`. Render a compact side-by-side table and divergence score.

**paths**: Extract two note-ids A and B. Call `mcp__mini-vinny__graph_expand(note_id=A, max_hops=3)` then trace shortest semantic path to B. Show the path with edge types.
