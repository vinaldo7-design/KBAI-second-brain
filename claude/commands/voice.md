---
description: Apply a voice from ~/.claude/voices/ to your response (single voice or "+"-separated combination)
---

Apply a voice (or fused combination) for the response that follows.

**Parse `$ARGUMENTS`:**
- First whitespace-delimited token = voice spec (single name like `naval` or combo like `naval+bourdain`)
- Everything after = the actual query/instruction

**Voice loading:**

For each voice name in the spec:
- If voice == `vinay`: call `mcp__mini-vinny__assemble_context(query="voice exemplar", seed_k=10)` and filter for notes whose frontmatter contains `voice-exemplar: true` (read with `mcp__mini-vinny__get_note_with_context`). Use those passages as the voice prior. If no exemplar notes exist yet, say so explicitly and offer to help identify candidates.
- Otherwise: read `~/.claude/voices/<name>.md`. Use its style rules, anti-patterns, and exemplars as the voice prior.

**Combination logic** (when spec contains `+`):

Don't mechanically merge — voices conflict if you try. Instead, write a brief synthesis prompt for yourself: which dimensions you'll take from voice A (length? structure?) and which from voice B (register? persona?). Use the `combines_well_with` / `combines_poorly_with` frontmatter as a sanity check — warn the user once if they're combining poorly-paired voices, then proceed anyway. Aim for the strongest hybrid, not the average.

Example for `naval+bourdain`:
- Length & structure from Naval (short, aphoristic)
- Register & persona from Bourdain (vernacular, observer)
- Result: short observational sentences that land like Naval but feel lived-in like Bourdain

**Response:**

Apply the voice consistently for the entire response. Don't break character to explain what you're doing. If there's no query (just a voice spec), confirm the voice is loaded and apply it to the next message.

If the voice doesn't exist (no file at `~/.claude/voices/<name>.md`), list the available voices from that directory and stop.
