# Stage 0 notes — multi-agent refactor

Tracks scaffolding work that does not change behaviour. Stage 0 is about
invariants and naming, not new features.

**Status: ☑ all items complete** (verified 95/95 tests passing in `minivinnymcp` conda env, 2026-05-10).

---

## Item 1 — namespaced tool aliases ☑

Underscore-namespaced aliases added on Mini Vinny (MCP spec disallows dots).

| Legacy (kept) | Namespaced (new) |
|---|---|
| `vault_search` | `retrieve_search` |
| `assemble_context` | `retrieve_assemble` |
| `get_note_with_context` | `notes_get_with_context` |

`graph_expand`, `audit_taxonomy` already namespaced. Perplexity left alone (`apply_research` migrates to Write Agent in Stage 3).

**Files**: `minivinnymcp/server.py` (+3 `_*_impl` helpers), `minivinnymcp/tests/test_tool_aliases.py` (new).

---

## Item 2 — `challenges` taxonomy drift ☑

Static fallback `TYPED_LINK_SECTIONS` in `vault_graph.py` was missing `challenges`, `exemplifies`, `operationalises` — yaml is canonical and was already loading them at runtime, but the fallback path would crash on yaml-missing systems and the docstring listed an outdated 7-type set.

Synced fallback to all yaml-declared types with `section_heading`. Added `test_taxonomy_drift.py` — fails fast if yaml grows a section heading the fallback doesn't carry.

**Files**: `vault_graph.py` (docstring + dict), `minivinnymcp/tests/test_taxonomy_drift.py` (new).

---

## Item 3 — `mentioned` mode formalisation + exhaustive mode ☑

Three retrieval modes now defined (`RETRIEVAL_MODES`):

| mode | PPR exclude | Path-attribution exclude |
|---|---|---|
| `standard` (default) | `contradicts`, `mentioned` | `contradicts`, `referenced-in`, `untyped`, `mentioned` |
| `sparring` | `mentioned` | `referenced-in`, `untyped`, `mentioned` |
| `exhaustive` | (none) | `referenced-in`, `untyped` |

`exhaustive` lazy-loads a separate `VaultGraph` with `include_mentioned=True`. Synthetic-graph test confirms `mentioned`-only neighbours are unreachable in standard mode and reachable in exhaustive.

**Files**: `minivinnymcp/server.py` (+`_get_graph_exhaustive`, mode-gated exclude sets), `minivinnymcp/tests/test_mode_mentioned.py` (new).

---

## Item 4 — analytics_connect_suggest ☑

New module `kbai/analytics/connect_suggest.py` re-exports the five suggestion functions from `vault_connect_suggest.py` plus a unified `connect_suggest(graph, categories=None)` entry point. Exposed as MCP tool `analytics_connect_suggest` on Mini Vinny — read-only, never mutates. Stage 1 will move the implementations physically; Stage 0 just establishes the boundary.

**Files**: `kbai/__init__.py`, `kbai/analytics/{__init__.py, connect_suggest.py}`, `minivinnymcp/server.py` (+tool), `minivinnymcp/tests/test_analytics_connect_suggest.py` (new).

---

## Item 5 — writeagentmcp skeleton ☑

New package with two stub tools — both validate input, return well-formed stub receipts, never touch the vault.

| Tool | Behaviour |
|---|---|
| `write_append_research_section` | Validates note_id + payload; returns `{status:"stub", applied:false, would_apply:true, ...}`; calls reindex hooks (Item 8) for shape exercise |
| `write_apply_link_suggestions` | Validates list of suggestion dicts; counts valid vs invalid; never writes |

Server registers as `"write-agent"`. Real mutation logic lands Stage 3.

**Files**: `writeagentmcp/{__init__.py, server.py, requirements.txt, claude_desktop_config_snippet.json, tests/__init__.py, tests/test_write_stubs.py}`.

---

## Item 6 — golden-set sampler ☑

`kbai/eval/sample_queries_from_note_hits.py` reads `06-Maps/vault-embeddings.db::note_hits`, ranks query hashes by `surface_count × recency_weight` (linear decay 7→90 days), joins with `query_log` (populated by Item 10) to recover query text, writes `eval/golden_queries.draft.json`.

Until `query_log` accumulates entries, draft rows have `query_text: null` for the user to fill in manually. Item 10's instrumentation seeds `query_log` going forward.

**Files**: `kbai/eval/__init__.py`, `kbai/eval/sample_queries_from_note_hits.py`.

---

## Item 7 — eval runner stubs ☑

`kbai/eval/run_retrieval_eval.py` loads draft queries, calls `_assemble_context_impl(query, mode)`, prints `id | mode | latency | top-5 ids`. `--dry` flag skips actual retrieval (useful in CI).

Pre-push hook script at `scripts/pre-push-eval.sh` (executable; not yet wired into `.git/hooks/`). GitHub Actions stub at `.github/workflows/retrieval-eval.yml` — runs on PR, no failure gate (Stage 6 wires the metric thresholds).

**Files**: `kbai/eval/run_retrieval_eval.py`, `scripts/pre-push-eval.sh`, `.github/workflows/retrieval-eval.yml`.

---

## Item 8 — reindex policy hooks ☑

`kbai/embed/reindex_hooks.py::update_note_embeddings(note_id)` and `kbai/graph/reindex_hooks.py::update_note_edges(note_id)` — both stubs that log intent and return `{status:"stub", would_*:true}`. Wired into `write_append_research_section` so the call shape is exercised.

Test uses monkeypatch to spy on `vault_graph.build_graph` and `vault_embed.main` — confirms neither is called during a per-note reindex hook invocation.

**Files**: `kbai/embed/{__init__.py, reindex_hooks.py}`, `kbai/graph/{__init__.py, reindex_hooks.py}`, `writeagentmcp/server.py` (wiring).

---

## Item 9 — voice exemplar hashing ☑

`kbai/voice_profile/`:
- `hash.py::compute_voice_exemplar_hash(notes)` — sha256 over sorted (note_id, body_hash); order-independent, content-sensitive.
- `profile.py::VoiceProfile` — dataclass with `to_dict`/`from_dict`, plus `build_voice_profile`.
- `cache.py::save_cached_profile/load_cached_profile` — file-backed JSON cache at `06-Maps/voice-profiles/<hash>.json`.

Tests verify: hash stability under reordering, hash sensitivity to content + id changes, cache roundtrip, miss returns None.

**Files**: `kbai/voice_profile/{__init__.py, hash.py, profile.py, cache.py}`.

---

## Item 10 — instrumentation module ☑

`kbai/instrumentation/log.py` — single entry point for retrieval-side logging. Two writers, both best-effort:

| Function | Writes to | Schema |
|---|---|---|
| `record_note_hits(...)` | `note_hits` (legacy, unchanged) + `query_log` (new, additive) | `query_log(query_hash, query_text, first_seen, last_seen, seen_count)` with upsert |
| `log_retrieval_event(...)` | `retrieval_events` (new, additive) | `(ts, query_hash, mode, latency_ms, num_candidates, graph_nodes_touched, top_note_ids)` |

`minivinnymcp/server.py::_record_hits` is now a 2-line shim over `record_note_hits`. Behaviour is preserved for existing consumers; query text is captured going forward to unblock the golden-set sampler (Item 6).

**Files**: `kbai/instrumentation/{__init__.py, log.py}`, `minivinnymcp/server.py` (shim).

---

## TODOs carried to Stage 1+

- Slash commands at `claude/commands/*.md` still reference legacy MCP names. Migrate during Stage 5 router work; drop legacy aliases at end of Stage 5.
- `vault_connect_suggest.py` still has 400+ LOC of implementations. Stage 1 physically moves them into `kbai/analytics/connect_suggest.py`; the CLI becomes a thin caller.
- `note_hits` lives inside `vault-embeddings.db`. Stage 1 separates instrumentation into its own DB (`06-Maps/instrumentation.db`).
- `kbai/embed/reindex_hooks.py` and `kbai/graph/reindex_hooks.py` are stubs. Stage 1 ports incremental embed (per-note hash check from `vault_embed.py`) and incremental edge parse.
- VoiceProfile is an empty dataclass. Real synthesis from `voice-exemplar: true` notes lands once Milestone 4 (`/voice vinay` activation) goes live.
- After merging: restart Claude Desktop so the MCP tool list refreshes (8 mini-vinny tools instead of 5).
