---
description: Run Perplexity Deep Research on a vault note, present findings, apply selectively
---

Run external research on a vault note using Perplexity Deep Research. Cost: ~$0.05–0.20 per call.

## Step 0 — resolve note ref

Call `mcp__mini-vinny__vault_search(query="$ARGUMENTS", top_k=5)`.

- If top score >= 0.7: resolve to that note_id, print `Resolved: [[<note_id>]] (score <confidence>)`, continue.
- If 0.4 <= top score < 0.7: print candidates and ask user to pick. Stop.
- If top score < 0.4: print `No matching note found for "$ARGUMENTS".` Stop.

## Step 1 — cost guard

Check `06-Maps/perplexity-research.db` for recent research on this note:
```
SELECT researched_at FROM research_log WHERE note_id = "<resolved_id>" ORDER BY researched_at DESC LIMIT 1
```
If the most recent entry is within the last 14 days, ask: *"This note was researched on YYYY-MM-DD. Re-run anyway? (y/n)"* — wait for confirmation.

## Step 2 — research

Call `mcp__perplexity-research__research_note(note_id=<resolved_id>, mode="single")`. Note: this call may take 30–60 seconds.

## Step 3 — present findings

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

## Step 4 — apply

Ask: *"Which to apply? (e.g. `sources 1,3 + claims all + cross-links 2 + raw`)"* — wait for reply.

Parse selection, call `mcp__perplexity-research__apply_research(note_id=<resolved_id>, sources=<selected>, claim_checks=<selected>, cross_links=<selected>, open_questions=<selected>, raw_summary=<text or empty>, include_raw_summary=<bool>, researched_at=<from step 2>)`.

Confirm: *"Appended to <file path>. Original prose untouched."*

Hard rules:
- Never call `apply_research` without explicit user selection.
- Never edit the note's main body — `apply_research` only appends a marked section.
