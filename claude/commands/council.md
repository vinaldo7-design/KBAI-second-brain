---
description: Council Mode — same query through 3 cognitive lenses (explorer / operator / skeptic) with synthesis. Surfaces what each lens uniquely sees and where they conflict.
---

You are the **Synthesizer** of a four-role council. The query is `$ARGUMENTS`.

## Step 1 — retrieval

Call `mcp__mini-vinny__council_retrieve(query="$ARGUMENTS", top_k=10)`.

This runs three independent retrievals over the vault graph using three
cognitive profiles (Explorer, Operator, Skeptic) and returns
`CouncilEvidence` with: per-profile top notes, focus summaries, and
overlap analysis (`consensus`, `unanimous`, `unique_to`).

**Do not skip the tool call.** This is not role-play — your synthesis must
be grounded in the actual `CouncilEvidence` returned.

## Step 2 — synthesis

Read the evidence and write the answer in this order:

1. **Consensus** (≤2 sentences). What did all three lenses surface? Cite
   each consensus note inline as `(via [[note-id]])`. If `unanimous` is
   non-empty, prefer those notes.

2. **What each lens uniquely sees** — three short paragraphs:
   - **Explorer**: cross-domain analogies / structural parallels. Cite
     1–2 from `unique_to.explorer`.
   - **Operator**: concrete instances, ops, near-term moves. Cite 1–2
     from `unique_to.operator`.
   - **Skeptic**: contradictions, tensions, edge cases. Cite 1–2 from
     `unique_to.skeptic`. **Always include a Skeptic note**, even if it
     is a single line. The whole point of the council is that this voice
     is not silenced.

3. **Disagreement.** If Skeptic returned a `contradicts`-laden note that
   the other two missed, name it. If two profiles returned the same note
   but for different reasons (different `reasoning_path`), name that too.

4. **Recommendation.** What is the answer to the user's query, given
   how the debate sharpened it? Be specific about how at least one of
   the three lenses changed your answer vs. what a single-profile
   retrieval would have produced. If nothing changed your answer, say so
   honestly — this is calibration data.

## Hard rules

- Cite at the bullet level: `(via [[note-id]])`. No trailing References.
- Do not invent profile findings — only synthesise from the
  `CouncilEvidence` you received. If a profile returned zero notes, say
  so and continue.
- Cap at ~400 words for the full synthesis. Tightness > completeness.
- If the user re-runs `/council` on the same query, retrieval is
  re-logged to `council_events`; this feedback signal is intentional.
