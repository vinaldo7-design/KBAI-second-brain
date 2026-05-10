---
description: Run Perplexity Deep Research on a vault note, present findings, apply selectively
---

Run external research on a vault note using Perplexity Deep Research. Cost: ~$0.05–0.20 per call.

1. **Cost guard first.** Check `06-Maps/perplexity-research.db` for recent research on this note:
   ```
   SELECT researched_at FROM research_log WHERE note_id = "$ARGUMENTS" ORDER BY researched_at DESC LIMIT 1
   ```
   If the most recent entry is within the last 14 days, ask the user: *"This note was researched on YYYY-MM-DD. Re-run anyway? (y/n)"* — wait for confirmation.

2. Call `mcp__perplexity-research__research_note(note_id="$ARGUMENTS", mode="single")`. Note: this call may take 30–60 seconds.

3. Present findings as a single compact menu (one block, no prose between sections):
   ```
   Sources:
     1. <title> — <url>
     2. ...
   Claims:
     1. "<snippet>" — <verdict>
     2. ...
   Cross-links:
     1. <hint> → [[<vault_note_id>]] (or "no match")
     2. ...
   Questions:
     1. <question>
     2. ...
   ```

4. Ask: *"Which to apply? (e.g. `sources 1,3 + claims all + cross-links 2 + raw`)"* — wait for reply.

5. Parse selection, call `mcp__perplexity-research__apply_research(note_id, sources=<selected>, claim_checks=<selected>, cross_links=<selected>, open_questions=<selected>, raw_summary=<text or empty>, include_raw_summary=<bool>, researched_at=<from step 2>)`.

6. Confirm: *"Appended to <file path>. Original prose untouched."*

Hard rules:
- Never call `apply_research` without explicit user selection.
- Never edit the note's main body — `apply_research` only appends a marked section.
