# Multi-Agent Refactor — Master Plan

Single source of truth for the Mini Vinny → multi-agent refactor.
Every session (Claude Code, Claude Desktop, or human) reads this first.

**Status legend**: ☐ todo • ◐ in progress • ☑ done • ⏸ blocked

---

## Executive brief

Mini Vinny is a working personal-knowledge agent on top of an Obsidian vault.
The current shape is two MCP servers (mini-vinny retrieval + perplexity research)
plus slash commands and a voice library. It works, but the retrieval pipeline
is monolithic, the single-writer invariant is broken (Perplexity owns
`apply_research`), and there is no evaluation harness.

**Target**: four roles with clean boundaries.

| Role | Owns |
|---|---|
| Mini Vinny | Read-only vault retrieval + graph reasoning + **cognitive routing** |
| Perplexity | External research, no writes |
| Write Agent | The only mutator — every vault write goes through it, journaled |
| Claude | Orchestration, voice rendering, human-in-the-loop gates |

**Two fidelity axes**:
- **Voice fidelity** (rendering) — same content, different expression. Owned by Claude.
- **Thinking fidelity** (retrieval) — same graph, different traversal. Owned by Mini Vinny via cognitive profiles. The existing `mode="standard|sparring"` is the prototype. Stage 5.5 generalises it.

**Strategy**: refactor in place, behaviour-preserving. Six stages (0–6),
~5 sessions of work end to end. Stage 0 is pure scaffolding — naming,
invariants, stubs. No new behaviour until Stage 3.

Full architecture rationale: see [stage0-notes.md](stage0-notes.md) and the
audit transcript captured in `02-Learning/session-close-2026-05-10-*.md`.

---

## Tooling discipline (token-efficient working style)

Each Stage 0 item is annotated with the recommended surface:

- 🖥 **Code** — Claude Code CLI. Default for file edits and test runs.
- 🔍 **Perplexity** — `/research` slash command or direct Deep Research.
  Use for citations, current-best patterns, multi-agent framework comparisons.
- 💬 **Desktop** — this Claude Desktop surface. Vault thinking, voice,
  light orchestration. Avoid heavy refactors here.

**Rule of thumb**: if a task touches >2 code files, it belongs in Claude Code.
If it asks "what is the current best practice for X", it belongs in Perplexity.

---

## Stage 0 — inventory + scaffolding

Goal: invariants and module skeletons in place. No behaviour change.

### Item 1 — namespaced MCP tool aliases ☑
- 🖥 Code surface
- ☑ Add `retrieve_search`, `retrieve_assemble`, `notes_get_with_context` aliases
- ☑ Keep legacy names as aliases of `_*_impl`
- ☑ Tests asserting both names registered + dispatch to same impl
- ☑ `docs/stage0-notes.md` updated
- ☐ Run `pytest minivinnymcp/tests/test_tool_aliases.py` (do this in Code)
- ☐ Restart Claude Desktop after merge so MCP refreshes

### Item 2 — `challenges` taxonomy drift ☑
- 🖥 Code surface
- Note: `challenges` exists in `vault_taxonomy.yaml` (default_weight 0.80) but
  is not in the `TYPED_LINK_SECTIONS` constant in `vault_graph.py:35`. Drift.
- ☐ Add `"challenges": "challenges"` to `TYPED_LINK_SECTIONS`
- ☐ Re-run `python vault_graph.py <vault>` to surface any latent challenges edges
- ☐ Add a unit test that walks `vault_taxonomy.yaml` and asserts every edge
  type with a `section_heading` is present in the parser's typed-section map.
  Fails fast on future drift.
- ☐ Commit with message `fix: surface challenges edge type in graph builder`

### Item 3 — `mentioned` edge mode formalisation ☑
- 🖥 Code surface (edits) + 🔍 Perplexity (one query, optional)
- ☐ Confirm `mentioned` is excluded from PPR walk in standard mode
  (currently is, via path_exclude — but PPR walk itself doesn't gate it; verify)
- ☐ Introduce `mode="exhaustive"` in `_assemble_context_impl` — allows
  mentioned-only neighbours, marks them `low_signal: true` in result
- ☐ Synthetic-graph unit test: build 3-node graph where C is reachable only
  via `mentioned`. Assert C absent in standard, present + flagged in exhaustive.
- ☐ Document the new mode in `docs/stage0-notes.md`
- 🔍 Optional Perplexity query: "common patterns for marking low-signal
  retrieval results in RAG systems" — cite into the doc

### Item 4 — split connect-suggest into analytics vs write ☑
- 🖥 Code surface
- ☐ Create `kbai/analytics/connect_suggest.py` (new package layout)
- ☐ Move pure read functions from `vault_connect_suggest.py` into it
- ☐ Keep markdown-rendering at the CLI level for now (defer move)
- ☐ Add MCP tool `analytics_connect_suggest` on Mini Vinny — wraps the pure fn
- ☐ Fixture-graph test for deterministic output
- ☐ `vault_connect_suggest.py` becomes a thin CLI calling `kbai.analytics.connect_suggest`

### Item 5 — `writeagentmcp` skeleton ☑
- 🖥 Code surface
- ☐ Create `writeagentmcp/{__init__.py, server.py, requirements.txt, tests/, claude_desktop_config_snippet.json}`
- ☐ Stub tools (no real writes yet):
  - `write_append_research_section(note_id, payload, dryrun=True)` → returns
    `{"would_apply": True, "diff_preview": str, "target_file": str}`
  - `write_apply_link_suggestions(suggestions, dryrun=True)` → similar
- ☐ Tests: server starts; tools return well-formed stub responses; never
  touches the real vault when `dryrun=True`
- ☐ Add to `claude_desktop_config_snippet.json` for future activation
- 🔍 Optional Perplexity query: "MCP server pattern for write-with-journal +
  dryrun in Python" — cite into stage0-notes if it surfaces something useful

### Item 6 — golden-set eval scaffolding ☑ (sampler + draft pipeline; query_text capture wired via Item 10)
- 🔍 Perplexity-heavy + 🖥 Code (light)
- ☐ Create `kbai/eval/sample_queries_from_note_hits.py`
- ☐ Reads `06-Maps/vault-embeddings.db::note_hits`, samples ~30 queries
  weighted by recency × surface count
- ☐ Writes `eval/golden_queries.draft.json` (queries only, no expected
  rankings yet — that's Item 6 part 2)
- 🔍 **Use Perplexity (or `/research` on a meta-note) to propose** what each
  golden query *should* surface. Hand back a draft for you to accept/reject.
  Token cost lives in Perplexity, not in chat context.
- ☐ Final: `eval/golden_set.yaml` with `tier1` (must-surface in top-5) and
  `tier2` (should-surface in top-15) per query

### Item 7 — eval runner stubs ☑
- 🖥 Code surface
- ☐ `kbai/eval/run_retrieval_eval.py`:
  - loads `eval/golden_queries.draft.json` (or final yaml if exists)
  - calls `_assemble_context_impl(query, mode="standard")`
  - prints `query | top-5 ids | mode | latency_ms` per row
  - exit 0 always at this stage (no thresholds yet)
- ☐ `scripts/pre-push-eval.sh` — calls the runner; not wired into git hooks yet
- ☐ `.github/workflows/retrieval-eval.yml` stub — runs on PR, no failure gate
- ☐ Test: `python kbai/eval/run_retrieval_eval.py --dry` works on empty queries

### Item 8 — reindex policy hooks ☑
- 🖥 Code surface
- ☐ `kbai/embed/reindex_hooks.py::update_note_embeddings(note_id)` — logs
  "would re-embed note X" for now
- ☐ `kbai/graph/reindex_hooks.py::update_note_edges(note_id)` — logs
  "would re-parse edges for note X" for now
- ☐ Wire stubs from Write Agent stub tools (Item 5) so the call shape is
  exercised even though the work is deferred
- ☐ Tests: functions exist, accept a single note_id, do not trigger a
  full graph rebuild (use mocks/spies)

### Item 9 — voice exemplar hashing ☑
- 🖥 Code surface
- ☐ `kbai/voice_profile/hash.py::compute_voice_exemplar_hash(notes) -> str`
  — sha256 of sorted (note_id, body_hash) tuples
- ☐ `kbai/voice_profile/profile.py::build_voice_profile(hash) -> VoiceProfile`
  — placeholder dataclass, real synthesis later
- ☐ `kbai/voice_profile/cache.py::load_cached_profile / save_cached_profile`
- ☐ Tests:
  - same content → same hash
  - any exemplar's body change → different hash
  - cache roundtrip preserves profile

### Item 10 — instrumentation module ☑
- 🖥 Code surface
- ☐ Create `kbai/instrumentation/log.py::log_retrieval_event(...)`
- ☐ Schema: `(query_hash, mode, latency_ms, num_candidates, graph_nodes_touched, top_note_ids, ts)`
- ☐ For Stage 0, **keep writing to `vault-embeddings.db::note_hits`** — schema
  migration to its own DB happens in Stage 1 (separation of stores).
- ☐ Replace `_record_hits` calls in `_assemble_context_impl` with calls to the
  new helper. Behaviour preserved.
- ☐ Test: calling `log_retrieval_event` writes a row with the expected columns.

---

## Stage 0 verification checklist

Run before declaring Stage 0 done. Do this in Claude Code:

```bash
cd "<vault root>"

# IMPORTANT: tests need the minivinnymcp conda env (mcp + sentence-transformers).
# The base anaconda env will fail with ModuleNotFoundError: mcp.
PYTEST=/Users/vinaynair/opt/anaconda3/envs/minivinnymcp/bin/pytest

$PYTEST minivinnymcp/tests/ perplexitymcp/tests/  # all 48 baseline + aliases
$PYTEST writeagentmcp/tests/                       # new package
python kbai/eval/run_retrieval_eval.py             # smoke runs
python vault_graph.py "$PWD"                        # rebuilds with challenges fix
git diff --stat docs/                               # stage0-notes + this file updated
```

All green → tag `stage-0` → start Stage 1.

**Item 1 verification** (✅ 2026-05-10):
- `test_tool_aliases.py` — 5/5 passed in `minivinnymcp` conda env.
- Mini Vinny exposes 8 tools (5 legacy + 3 namespaced).

**Stage 0 full verification** (✅ 2026-05-10):
- `pytest minivinnymcp/tests/ perplexitymcp/tests/ writeagentmcp/tests/` — **95/95 passed** in `minivinnymcp` conda env.
- 9 new tools registered across 3 servers (8 mini-vinny + 2 stub write-agent).
- New `kbai/` package skeleton: `analytics`, `embed`, `eval`, `graph`, `instrumentation`, `voice_profile`.
- `note_hits` schema preserved; new `query_log` and `retrieval_events` tables additive.

**Stage 5.6 verification** (✅ 2026-05-10):
- **153/153 tests passing** in `minivinnymcp` env (28 new across council + cognitive routing + contracts).
- 12 new MCP tools live across mini-vinny (was 5 → now 13: 8 from earlier stages + cognition_list_profiles + cognition_get_profile + cognition_retrieve_as + council_retrieve + analytics_connect_suggest).
- Council differentiation proven on synthetic graph: weight_overrides demonstrably re-rank PPR (test_skeptic_admits_contradicts_and_boosts_E, test_explorer_boost_raises_C).
- Live smoke test ran council_retrieve against the real vault graph successfully.
- New `council_events` SQLite table — feedback signal accumulating from `/council` calls.
- `_assemble_context_impl` (the existing single-profile entry point) was NOT touched. Stage 5.5.3 in Code can proceed cleanly.

**Stage 1 partial verification** (✅ 2026-05-10):
- pyproject.toml declares `kbai`, `minivinnymcp`, `perplexitymcp`, `writeagentmcp` as installable packages (not yet installed).
- `connect_suggest` 5 categories + helpers physically live in `kbai/analytics/connect_suggest.py`. `vault_connect_suggest.py` is now a 150-line CLI wrapper that re-exports for backward compat.
- `_find_note_file` deduplicated — both servers shim to `kbai/storage/note_io.py::find_note_file`. 9 new tests cover path-input, node-metadata, rglob fallback, and missing-file cases.
- **104/104 tests passing**, no regression.
- **Deferred to Claude Code**: 1.2 (graph_loader/vault_search physical moves), 1.4 (assemble_context decomposition), 1.5 (trace verification). These need a fresh-context session for safety.

---

## Stages 1–6 — outline (detail expanded as we get there)

### Stage 1 — module extraction (behaviour-preserving)
- Create `kbai/` package; move `vault_graph_loader.py` → `kbai/graph/engine.py`,
  `vault_graph.py` → `kbai/graph/builder.py`, `vault_embed.py` → `kbai/embed/indexer.py`,
  `vault_search.py` → `kbai/embed/encoder.py`.
- Add `pyproject.toml`; kill `sys.path.insert(0, vault_root)` hacks.
- Dedupe `_find_note_file` into `kbai/storage/note_io.py`.
- MCP servers shrink to thin adapters (each tool body ≤ 5 lines).
- ☑ Item 1.1 — pyproject.toml metadata declared (no `pip install -e` yet — Stage 1.4 will trigger)
- ◐ Item 1.2 — partial: connect_suggest impls physically moved into `kbai/analytics/`. Graph/embed/parser moves deferred to Code session (heavy file shuffles)
- ☑ Item 1.3 — `_find_note_file` deduped; both servers shim to `kbai/storage/note_io.py`
- ☐ Item 1.4 — `_assemble_context_impl` decomposition into `kbai/retrieve/{dense,ppr,path,assembler}.py` (heavy refactor — defer to Code)
- ☐ Item 1.5 — baseline traces match within 1% (Item 7 runner is the check)

### Stage 2 — typed contracts
- `kbai/contracts.py` Pydantic models: RetrievalResult, Context, Note, Edge,
  ResearchPayload, WriteReceipt.
- Adapters serialise via `.model_dump()` at MCP boundary.
- ☐ Items 2.1–2.5 (one per major contract)

### Stage 3 — Write Agent goes live
- Move `apply_research` from perplexitymcp → writeagentmcp (rename to
  `write_append_research_section`).
- Implement real `write_patch_typed_link` (port `pile_a_patcher.patch_section`).
- `write_journal.db` records every mutation.
- `/research` slash command updated to call new tool.
- ☐ Items 3.1–3.6

### Stage 4 — research split clean
- Add `research_cluster`, `research_verify_claim` to perplexitymcp.
- Static check: perplexity package has zero `write_text` references.
- ☐ Items 4.1–4.3

### Stage 5 — orchestration / router
- `/ask <query>` slash command — deterministic intent classifier.
- Migrate slash commands to namespaced tool names.
- Drop legacy aliases (deprecation cycle complete).
- ☐ Items 5.1–5.4

### Stage 5.5 — Cognitive routing v1 (thinking fidelity)
**Premise**: `mode="standard|sparring"` is already a binary cognitive profile.
Generalise it. Voice fidelity changes expression; thinking fidelity changes
retrieval, ranking, and path selection over the same graph.

**Constraints (hard)**:
- Ship *functional* profiles only in v1: `default`, `skeptic`, `operator`, `builder`.
  Do **not** ship `vinay` or any person-named profile until Stage 8 calibration.
  A profile named after a person is a claim to model a mind; we can't back it.
- Profiles modify retrieval, never rendering. Voice is orthogonal.
- Every profile must produce different top-N than `default` on at least 50% of
  queries — otherwise it's noise. Compare-thinkers (Stage 5.6) enforces this.

**Schema** (`kbai/cognitive_routing/profile.py`):
```python
class CognitiveProfile(BaseModel):
    profile_id: str
    display_name: str
    schema_version: int = 1
    edge_weight_overrides: dict[str, float] = {}   # multiplies taxonomy weight
    contradiction_policy: Literal["suppress","allow","seek"] = "suppress"
    mention_policy: Literal["ignore","exhaustive"] = "ignore"
    path_length_preference: Literal["short","balanced","deep"] = "balanced"
    abstraction_preference: Literal["concrete","balanced","abstract"] = "balanced"
    restart_bias_tags: dict[str, float] = {}        # tag → personalization boost
    confidence_threshold: float = 0.0
    notes: str = ""                                  # human description
```

- ☐ 5.5.1 — `kbai/cognitive_routing/{profile.py, registry.py, applier.py}`
- ☐ 5.5.2 — Profile registry: YAML files at `kbai/cognitive_routing/profiles/*.yaml`
- ☐ 5.5.3 — Refactor `_assemble_context_impl` to take `profile_id` (default `"default"`).
  Old `mode` arg maps to profile (`"standard"→"default"`, `"sparring"→"skeptic"`)
  for one deprecation cycle.
- ☐ 5.5.4 — Apply overrides to PPR transition matrix + path_exclude set
- ☐ 5.5.5 — New tools: `cognition_list_profiles`, `cognition_get_profile`, `cognition_retrieve_as`
- ☐ 5.5.6 — Slash command `/think <profile> <query>`
- ☐ 5.5.7 — Tests: synthetic graph, assert each profile produces different top-N

### Stage 5.6 — Council Mode + compare-thinkers
**Premise**: same query through N profiles, with a synthesizer (Claude) reading
the bundle. Council Mode is the opinionated 3-profile preset (explorer +
operator + skeptic). Compare-thinkers is the raw multi-profile primitive.
They share the same retrieval primitive.

- ☑ 5.6.1 — `weight_overrides` parameter added to `VaultGraph.ppr_expand`
  (lets profile edge-weight multipliers actually take effect; default behaviour
  unchanged when not passed).
- ☑ 5.6.2 — `explorer` profile YAML shipped (analogous-to + exemplifies bias).
- ☑ 5.6.3 — `CouncilEvidence` + `CouncilProfileResult` Pydantic models in
  `kbai/contracts.py`.
- ☑ 5.6.4 — `kbai/council/` package: `run_council`, `build_council_evidence`
  (pure overlap math), `profile_focus_summary`, `DEFAULT_COUNCIL_PROFILES`.
- ☑ 5.6.5 — Server: `_assemble_context_with_profile` (profile-aware retrieval
  parallel to `_assemble_context_impl`, doesn't disturb existing tool).
- ☑ 5.6.6 — MCP tools: `cognition_retrieve_as`, `council_retrieve`.
- ☑ 5.6.7 — Feedback capture: `record_council_event` writes to a new
  `council_events` table on every `/council` invocation. Stage 8 calibration
  reads this to correlate profiles → notes the user later acts on.
- ☑ 5.6.8 — `claude/commands/council.md` — synthesizer prompt with hard
  rules: must call the tool (no role-play), must include a Skeptic note,
  must explain how the debate sharpened the answer.
- ☐ 5.6.9 — `cognition_compare_profiles(query, profile_ids[]) -> ProfileComparison`
  (raw primitive without synthesis prompt; lower priority than Council).
- ☐ 5.6.10 — Slash command `/compare-thinkers <p1>+<p2> <query>`.

### Stage 6 — eval harness production
- Wire `eval/run_retrieval_eval.py` into pre-push hook (mandatory).
- GitHub Actions PR gate: MRR drop > 5% blocks merge.
- Monthly Perplexity audit on canonical queries.
- ☐ Items 6.1–6.5

### Stage 7 — per-profile evaluation
- ☐ Extend golden set with per-profile expected outcomes
  (e.g. `skeptic` queries should surface contradicts-rich neighbourhoods)
- ☐ Metrics: profile-divergence rate, profile-internal coherence
- ☐ A profile fails review if it doesn't beat `default` on its target query class

### Stage 8 — profile calibration (`vinay` becomes earnable)
- ☐ Mine `note_hits` for query→note retrieval-success patterns
- ☐ Fit edge-weight overrides that maximise observed surfacing of "kept" notes
- ☐ Resulting profile is `vinay-v1` — versioned, falsifiable
- ☐ Hard requirement: the calibrated profile must beat hand-authored profiles on
  Stage 7 metrics, or it doesn't ship.

---

## Decision log (open questions from the audit)

These are decisions I'm tracking so I don't re-litigate them mid-stage.

| # | Question | Decision | Status |
|---|---|---|---|
| 1 | Tool namespacing: dots vs underscores | Underscores (MCP spec) | ☑ locked |
| 2 | Three MCP servers vs one | Three (separate process for Write Agent) | ☑ locked |
| 3 | Write Agent autonomy: explicit confirmation? | Yes — keep human gate | ☑ locked |
| 4 | Golden-set authorship | Drafted from `note_hits` + Perplexity proposals; you cull | ☐ pending Item 6 |
| 5 | Reindex coupling: incremental vs batched | Incremental, scoped to touched note | ☑ locked |
| 6 | Voice exemplar: live vs cached | Cached; recompile on hash change (Item 9) | ☑ locked |
| 7 | Connect-suggest as MCP tool? | Yes — read-only at `analytics_connect_suggest` | ☑ locked (Item 4) |
| 8 | CI vs local-only eval | Both — pre-push hook + PR gate | ☑ locked |
| 9 | `challenges` taxonomy drift | Fix in Item 2 | ☐ pending |
| 10 | `mentioned` in retrieval | Never in standard; new exhaustive mode (Item 3) | ☑ locked |
| 11 | Person-named cognitive profiles (`vinay`, `girlfriend`, etc.) | **Reject in v1**. Ship functional profiles only (default, skeptic, operator, builder). `vinay` becomes earnable via calibration in Stage 8 against `note_hits`. Person-named profiles for "explain to person X" belong in voice/audience layer, not retrieval. | ☑ locked |
| 12 | Cognitive profile vs voice profile boundary | Cognitive = retrieval/ranking/path selection. Voice = expression. Never overlap. | ☑ locked |
| 13 | `mode` parameter migration path | `mode="standard"→profile_id="default"`, `mode="sparring"→profile_id="skeptic"`. One deprecation cycle, then drop `mode`. | ☑ locked |

---

## Progress check protocol

Any future session begins with:

1. Read this file — find the first ☐ item under the active stage.
2. Confirm any ◐ in-progress items are still in flight (or revert).
3. Pick up the next ☐, propose edits, await go-ahead, apply.
4. Update checkboxes in this file in the same commit as the code.

If unsure where we are, run:
```bash
grep -n "☐\|◐" docs/refactor-plan.md | head -20
```
