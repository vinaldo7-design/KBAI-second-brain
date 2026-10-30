# Oxford ingestion pipeline

**Purpose.** Turn Oxford DipAI material (slides, transcripts, readings) into typed vault notes without duplicating what the vault already holds. Output per session: one `learning` note (origin lecture, author, context) plus `idea`/`concept` notes for every claim that passes the Core Claim test, all edged into the module map.

**Governing principle.** Parallelise the stateless step, serialise the stateful one. Extraction needs only the source and a snapshot of the vault, so N sessions run as N agents at once. Collision checking and writing touch shared state, so they run through one orchestrator, in order. Two agents writing concurrently is how the 2026-04-23 duplicate pairs happened.

**Batch size.** One module at a time (up to ~16 sessions). Within the batch, one agent per session.

---

## Stage 0 — Drop

`07-attachments/oxford-inbox/<M1..M4>/`. Name files so the session is recoverable: `M3-S04-xai-slides.pptx`, `M3-S04-transcript.vtt`. The inbox is in `vault_graph.py` SKIP_DIRS.

## Stage 1 — Convert (mechanical, Cowork shell)

```
python3 scripts/ingest_convert.py            # idempotent; --force to redo; --module M3 to scope
python3 vault_graph.py . && python3 scripts/ingest_snapshot.py   # fresh vault snapshot for the agents
```

Produces `_md/<module>__<stem>.<ext>.md`, `_manifest.json` (sha256, status), `_vault_snapshot.json` (id/type/tags/summary of every note, ~60 KB). The snapshot is the dedup instrument for agents that have no vault tools.

## Stage 2 — Extract (parallel, one agent per session)

Orchestrator groups `_md` files by session (slides + transcript + readings for S04 go to one agent), stages them plus `_vault_snapshot.json` into the container, launches one agent per session with the brief below, and collects `candidates/<module>-<session>.json`.

Agents do not touch the vault. They read, extract, and pre-check every candidate against the snapshot. Their output is a proposal, not a write.

## Stage 3 — Collision check and merge (orchestrator, serial)

For every candidate across all agents, in order:
1. `retrieve_search(summary, top_k=10)` (10, not 5, since the vault passed 500 notes); if any hit scores above the collision threshold (empirically ~0.75 cosine distance in this index; lower is closer), read it with `get_note_with_context` and decide: **skip** (already held), **append** (existing note gains a section or an edge), or **create**.
2. Cross-agent dedup: two sessions proposing the same idea collapse into one candidate with both sessions as provenance.
3. Edge targets must exist (snapshot ids) or be in the same batch.

Never `obsidian_simple_search` for this step (silent false negatives).

## Stage 4 — Review

One table: candidate id, type, folder, one-line summary, action (create/append/skip), edges, source session. Vinay approves, strikes, or retypes. Nothing is written before this.

## Stage 5 — Push (orchestrator, serial)

After approval the orchestrator writes `07-attachments/oxford-inbox/_payloads_<module>.json` (list of {folder, note_id, frontmatter, body}, pre-validated against `kbai/schema.py`) . `make ingest M=<module>` then runs the push NATIVELY on the Mac via `scripts/ingest_push.py`, which calls the write agent's own `create_note` for every payload (schema gate, journal, on-write embedding and edge hooks, no overwrite), then rebuilds the graph and runs the healthcheck. 83 notes took 66 seconds on M1. Launch it by double-clicking the `.command` in Finder (Claude can do this through desktop control) or from a terminal. One MCP `write_create_note` call per note also works but costs ~25 s per note through the bridge.

Then the orchestrator reverse-patches existing notes (symmetric types and the builds pair get their mirror line; `challenges`, `exemplifies`, `operationalises` stay one-way), marks the manifest `pushed`, and refreshes the snapshot.
From the Cowork shell: `python3 vault_graph.py . && python3 scripts/vault_audit.py && python3 scripts/ingest_snapshot.py`.

The re-embed is not optional: the next batch's collision check reads the index.

Lessons from the first four modules (2026-10-01 to 02), now rules:
- **Numeric ids must not collide across batches.** `ingest_push.py` refuses the whole payload if any frontmatter `id` is already in the vault or repeats inside the batch. Start each batch's id counter after the highest id of the same date.
- **Mirror edges inside the batch too.** The reverse-patch only covers edges that point at pre-existing notes; `builds-on`/`builds-toward`, `contradicts` and `analogous-to` between two notes of the same batch need their mirror line written by the build. Check with `analytics_connect_suggest(["missing_bidir"])` after the push; it should return nothing for the new notes.
- **Do not cap an edge type in a review brief.** A cap on `contradicts` pushed real contradictions into `challenges`. Give reviewers the test (can both notes be true at once?) and no quota.
- **Apply bulk links with `make links FILE=<file>`.** It checks the whole list first, keeps reasons, writes mirrors, journals every line, snapshots the notes and runs the audit.

---

## Extraction agent brief (verbatim, per session)

> You are extracting vault notes from one Oxford Saïd DipAI session. Inputs: the session's markdown files (slides and/or transcript and/or readings) and `_vault_snapshot.json`, a list of every note the vault already holds with its summary.
>
> Produce `candidates/<module>-<session>.json` with this shape:
> ```json
> {"session": {"module": "M3", "session": "S04", "title": "...", "lecturer": "...", "date": "..."},
>  "learning_note": {"id": "kebab-id", "summary": "one sentence for LLM retrieval", "key_claims": "prose, 200-400 words, written for a future LLM reading cold", "quotes": ["<15 words each"], "tags": ["topic/...", "lens/academic"]},
>  "candidates": [
>    {"id": "kebab-id", "type": "idea|concept", "core_claim": "ONE sentence; if you cannot write it, do not propose the note",
>     "summary": "one sentence", "body": {"the_idea": "...", "the_tension": "...", "cross_domain": "..."},
>     "tags": ["topic/...", "lens/..."],
>     "edges": [{"type": "builds-on|builds-toward|contradicts|analogous-to|exemplifies|challenges|operationalises", "target": "existing-or-batch-id", "why": "one line"}],
>     "snapshot_check": {"closest": ["id1", "id2"], "verdict": "new|overlaps|duplicate", "reason": "one line"},
>     "source": "slide 12 / transcript 00:41"}
>  ]}
> ```
> Rules. Lenses are only academic, strategic, philosophical, personal, substack, professional. Tags kebab-case. The unit is the session: slides give structure and citations, the transcript carries the argument. Propose an idea note only when the core claim can be written in one sentence; otherwise fold it into the learning note. Mark `duplicate` when the snapshot already states the claim (then propose an edge from the learning note instead), `overlaps` when a note is adjacent but the claim differs, `new` otherwise; every candidate needs at least two edges to existing ids. Cite named sources (author, year) in the body. Do not write to any vault. British spelling. No em-dashes.

## Why this shape

- The snapshot gives each agent a dedup instrument without giving it write access or a tool it could misuse.
- The orchestrator's serial pass is cheap because agents have already done the reading; it only adjudicates.
- Approval before write keeps the vault contract intact and keeps a bad extraction from costing a merge session later.
