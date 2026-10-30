# Refactor state + audit toolkit

**Purpose.** A running ledger of multi-phase refactor initiatives and the commands that audit their state. Read this when you want to know *exactly where we are* on long-running structural work, and when you want to run the same audits again.

Companion docs:
- `docs/refactor-plan.md` — the original multi-stage refactor roadmap (Stages 0–9, shipped 2026-05-12).
- `docs/phase-6-plan.md` — the body-template-consolidation plan from the drift-elimination arc (Phase 6, queued).
- `docs/operating-manual.md` — how to use the system end-to-end.

---

## Initiative ledger

### Drift elimination across the parser/writer membrane (2026-05-27)

Single source of truth for edge taxonomy (`vault_taxonomy.yaml`) and frontmatter (`kbai/schema.py`), executed at runtime on both read and write paths, gating exactly one journalled writer.

| Phase | Title | Status | Commit / artefacts |
|---|---|---|---|
| 1 | `graph_stats` audit honesty (raw vs collapsed columns) | ✅ shipped | `vault_graph_loader.py::graph_stats` |
| 2 | Loader preserves edges, collapse/filter at query time | ✅ shipped | `vault_graph_loader.py::view`; PPR parity via `minivinnymcp/tests/fixtures/ppr_baseline.json` |
| 3 | `section_patcher.py` reads `EDGE_HEADING` from yaml | ✅ shipped | `kbai/storage/section_patcher.py`; case-insensitive regex covers existing notes |
| 4 | `kbai/schema.py` single source + validator gate | ✅ shipped | `kbai/schema.py::validate_frontmatter`; both `vault_graph.py` and `note_creator.py` import from here |
| 5 | `apply_research` delegates to journalled writer | ✅ shipped | `perplexitymcp/server.py::apply_research` → `kbai/storage/research_appender.py::append_research_section` |
| 6 | Body template consolidation | ✅ shipped (6a–6c) | `kbai/templates/`, `kbai/templates.py`, `kbai/storage/note_creator.py` empty-body branch, `scripts/regenerate_obsidian_templates.py`, `kbai/schema.py::ALLOWED_LIFECYCLE_STAGES`, regenerated `Templates/*.md` (gitignored), `Templates/quick-capture.md` deleted, CLAUDE-static.md §4 updated |

Tests at close of Phase 6: **289 passing** (was 274 at end of Phase 5, 75 at start of the arc).
Commit shipping Phases 1–5: `85edddb` on `main`. Phase 6 changes pending commit.

**Phase 6 vault-content migrations explicitly deferred** (not in code scope):
1. **Heading-case rewrite** — existing notes with `### Referenced in Maps` etc. vs canonical `### Referenced in maps`. Cosmetic only — Phase 3's case-insensitive regex covers correctness. Run preview:
   ```bash
   grep -rnE '^### (Referenced in Maps|Builds On|Builds Toward|Contradicts|Analogous To|Exemplifies|Challenges|Operationalises)$' 00-Captures/ 01-Ideas/ 02-Learning/ 04-Substack/ 05-Personal/ 06-Maps/ 2>/dev/null | wc -l
   ```
2. **Status-value backfill** — existing capture/learning/essay notes have `status: unprocessed|processing|draft` (pre-Phase-4 vocabulary). The new `lifecycle_stage` field is the migration target: rewrite `status: unprocessed` → `status: seedling, lifecycle_stage: unprocessed`, etc. Validator only gates new writes; existing drift is silently tolerated.

**`/capture` workflow regression flagged** (Path A in 6b): the old slash command embedded a single `### Builds on` link from the closest neighbour. The prune dropped that. Restoring it means routing through `write_apply_link_suggestions` after `write_create_note` — one extra MCP call per `/capture`. Not done; awaiting explicit go.

### Multi-agent refactor (2026-05-12, prior session)

Stages 0–9 of the original refactor plan. See `02-Learning/session-close-2026-05-12-multi-agent-refactor-stage9.md` and `docs/refactor-plan.md`. Closed 2026-05-12 at commit `ebf3b79`.

---

## Audit toolkit

Each entry is a command you can run from the vault root, plus what it tells you. Re-run any time you want to verify state.

### Graph / edge taxonomy audits

```bash
python3 vault_graph_loader.py graph_stats
```
Prints `raw` (self.G, native types, mentioned included) vs `graph` (default view, collapsed, mentioned excluded) edge counts per yaml-listed type. Shows drift if any edge type appears in the graph but not in `vault_taxonomy.yaml`. Expected: drift = 0.

```bash
python3 vault_graph_loader.py distribution
python3 vault_graph_loader.py orphans
python3 vault_graph_loader.py audit --type=<edge_type> --min-length=60
python3 vault_graph_loader.py central 20 --by=pagerank
```
Distribution / orphan / force-fit / centrality audits over the default view.

### Write-journal audit

```bash
sqlite3 06-Maps/write-journal.db "SELECT ts, tool, note_id, status, dryrun FROM mutations ORDER BY id DESC LIMIT 20;"
```
The 20 most recent mutations across `write_create_note`, `write_append_research_section`, `write_apply_link_suggestions`. Every vault-mutating write across the system lands here exactly once.

To find applies of a specific edge type (e.g., audit for any past `referenced-in` write that the pre-Phase-3 bug would have dropped silently):
```bash
sqlite3 06-Maps/write-journal.db "SELECT id, ts, note_id, status, payload_json FROM mutations WHERE tool='write_apply_link_suggestions' AND payload_json LIKE '%referenced-in%';"
```

To find any direct `note_file.write_text` calls outside the canonical writer (single-writer invariant check):
```bash
grep -rn '\.write_text\|\.write_bytes' --include='*.py' . \
  | grep -v __pycache__ \
  | grep -v kbai.egg-info \
  | grep -v /tests/ \
  | grep -v /eval/ \
  | grep -v kbai/voice_profile \
  | grep -v kbai/storage \
  | grep -v writeagentmcp/server.py \
  | grep -v vault_graph.py \
  | grep -v vault_connect_suggest.py
```
Expected: empty.

### Schema / drift-detector audits

```bash
python3 -m pytest writeagentmcp/tests/test_schema_validator.py -v
python3 -m pytest writeagentmcp/tests/test_section_patcher_yaml.py -v
```
The drift-detector tests assert that runtime-derived sets exactly equal their source set (yaml's `section_heading` keys, `kbai.schema` allowed-value sets). If any downstream code starts hardcoding a second copy, these fail.

### PPR / PageRank parity audit

```bash
python3 -m pytest minivinnymcp/tests/test_view_semantics.py -v
```
Asserts the post-Phase-2 default view reproduces pre-refactor PPR / PageRank scores byte-for-byte against `minivinnymcp/tests/fixtures/ppr_baseline.json`. Run this any time you touch the loader.

### Full test sweep

```bash
python -m pytest \
    minivinnymcp/tests/ writeagentmcp/tests/ -q
```
Run before committing any structural change. (Perplexity MCP server removed 2026-06-23; its test suite is gone.)

### Template skeleton audit (Phase 6)

```bash
python -m pytest writeagentmcp/tests/test_templates.py -v
```
Drift detectors for the kbai/templates/ ↔ schema/yaml relationship. If any skeleton goes out of sync with `ALLOWED_TYPES`, `EDGE_HEADING`, `ALLOWED_STATUSES`, or `ALLOWED_LIFECYCLE_STAGES`, these fail.

```bash
python scripts/regenerate_obsidian_templates.py
```
Idempotent. Run after editing any `kbai/templates/*.md`. Output should be "unchanged: ..." if the working tree is in sync.

### Vault content audits (no writes)

```bash
# Heading-style drift on link sections (cosmetic — case-insensitive regex covers correctness)
grep -rn '^### Referenced in Maps' 00-Captures/ 01-Ideas/ 02-Learning/ 04-Substack/ 05-Personal/ 06-Maps/ 2>/dev/null | wc -l

# Status-vocabulary drift (existing notes vs ALLOWED_STATUSES={seedling,evergreen})
grep -rh '^status:' 00-Captures/ 01-Ideas/ 02-Learning/ 04-Substack/ 05-Personal/ 2>/dev/null | sort -u
```

### Embedding/indexing audit

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('06-Maps/vault-embeddings.db')
print('indexed notes:', conn.execute('SELECT COUNT(*) FROM vec_notes').fetchone()[0])
conn.close()
"
```
Catches missing-embedding gaps after adding notes. Re-run `python3 vault_embed.py` and `python3 vault_graph.py <vault-root>` to rebuild after note additions.

---

## How to start a new refactor initiative (template)

The pattern that worked for the drift-elimination arc:

1. **Open with recon.** Spawn an Explore or general-purpose agent to map the surface area, OR do the recon yourself with `grep`/`Read`. Report findings and STOP for approval — do not propose code yet.
2. **Get the universal rules.** One sentence per rule. E.g., *preserve information at construction; transform at query time; audit tools bypass query-time transforms*. These shape every later decision.
3. **Sub-divide into phases.** Each phase ends at STOP. No chaining. If a phase reveals work outside its stated scope, flag in one line and wait.
4. **Capture parity fixtures BEFORE touching anything score-sensitive** (PPR, embedding scores, etc.). Pickle them under `*/tests/fixtures/`. Tests assert post-refactor matches.
5. **Use the drift-detector test pattern.** For any runtime-derived set of values (e.g., `EDGE_HEADING.keys()`, validator's accepted statuses), write a test asserting it equals its declared source. Catches silent drift if anyone hardcodes a second copy later.
6. **Validators return `WriteReceipt(status="error", message=reason)`** rather than raising — preserve the MCP boundary contract.
7. **Close the session by updating this file** (a new entry under "Initiative ledger") + the manifest + CLAUDE.md handoff.

---

*Last updated: 2026-05-27, session close after Phase 6 of drift-elimination arc — the six-phase initiative is now code-complete; two vault-content migrations explicitly deferred.*
