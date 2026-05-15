---
description: Imagination mode — propose new research domains by reading cluster shape around a seed note. Five modes — extend, fracture, bridge, deepen, historicise.
---

Read the cluster shape around a seed note and propose new research domains that would extend, fracture, bridge, deepen, or historicise the cluster's thinking.

## Usage

`/imagine <note ref> [mode] [k]`

- `mode` defaults to `fracture` (highest-leverage default — surfaces unexamined load-bearing assumptions).
- Other modes: `extend`, `bridge`, `deepen`, `historicise`.
- `k` defaults to 5.

## Step 0 — parse args

Split `$ARGUMENTS` by whitespace. The last token, if it matches one of `extend|fracture|bridge|deepen|historicise`, is the mode; remaining tokens are the note ref. If a digit token appears, treat it as `k`.

## Step 1 — resolve note ref

Call `mcp__mini-vinny__vault_search(query="<note ref>", top_k=5)`.

- If top score >= 0.7: resolve to that note_id, print `Resolved: [[<note_id>]] (score <confidence>)`, continue.
- If 0.4 <= top score < 0.7: print candidates and ask the user to pick. Stop.
- If top score < 0.4: print `No matching note found for "<note ref>".` Stop.

## Step 2 — call imagine

Call `mcp__mini-vinny__imagine(seed=<resolved_id>, mode=<mode>, depth=2, k=<k>)`.

If the response has `error`, print the error and stop.

## Step 3 — reason

The response contains:
- `cluster_signature` — structural fingerprint (size, edge_distribution, contradicts_ratio, load_bearing, frontier, thematic_vocabulary)
- `synthesis_prompt` — Claude-ready prompt instructing the exact mode brief

**Use the embedded `synthesis_prompt` as your reasoning instructions.** Follow it precisely. The prompt encodes the mode's brief, the cluster's structural targets (load-bearing nodes for `fracture`; frontier nodes for `extend`; etc.), and the required JSON shape per proposed domain.

Return the JSON list of `k` proposed domains exactly as the prompt specifies.

## Step 4 — reply

After the JSON list, add a single line: which proposed domain would shift the cluster's thinking most, and why.

Then a second line suggesting next action — typically: `Run /capture on the strongest domain to seed a stub note, then /research it.`

No preamble. No recap. Execute, then report.
