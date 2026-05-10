# Mini Vinny

A personal AI knowledge agent built on top of an Obsidian second brain. Combines a typed knowledge graph with local semantic search and Personalized PageRank retrieval to power graph-aware synthesis via Claude — with optional Perplexity Deep Research as an external annotator.

Built by [@vinaynair](https://github.com/vinaynair). Companion to the [Substack](https://substack.com) essay series on AI governance, architectural restraint, and building minimum capable systems.

---

## What It Does

The vault is an Obsidian knowledge graph — atomic notes connected by typed edges encoding semantic relationships (`builds-on`, `contradicts`, `analogous-to`, etc.). Mini Vinny is the AI layer on top: it retrieves structurally coherent context from the graph using a hybrid pipeline (dense embedding seed → typed-graph PPR walk → semantic-path attribution) and passes it to Claude for synthesis, sparring, or essay drafting.

Two MCP servers, each scoped to one concern:

**`mini-vinny`** — vault retrieval. Semantic search, typed graph traversal, PPR-based context assembly, taxonomy auditing.

**`perplexity-research`** — external annotator. Calls Perplexity Deep Research on a single note, returns structured findings (sources, claim checks, cross-links, open questions) for explicit user review before any patch lands.

Strict separation between the two: vault is authoritative for your own thinking; Perplexity adds external citations and current developments without ever rewriting your prose.

---

## Architecture

```
┌────────────────────┐  ┌────────────────────┐
│   mini-vinny MCP   │  │ perplexity-research│
│                    │  │       MCP          │
│ - vault_search     │  │                    │
│ - graph_expand     │  │ - research_note    │
│ - audit_taxonomy   │  │ - apply_research   │
│ - get_note_with    │  │                    │
│   _context         │  └─────────┬──────────┘
│ - assemble_context │            │
└─────────┬──────────┘            │
          │                       │
          ▼                       ▼
┌─────────────────────┐  ┌──────────────────┐
│  06-Maps/           │  │  Perplexity API  │
│  ├ vault-graph.json │  │  sonar-deep-     │
│  ├ vault-embeddings │  │  research        │
│  │   .db (sqlite-   │  └──────────────────┘
│  │   vec + hits)    │
│  └ perplexity-      │
│    research.db      │
└─────────────────────┘
```

---

## Build phases

**Phase 1 — Typed graph parser** (`vault_graph.py`, `vault_graph_loader.py`)
Parses Obsidian markdown into a typed JSON graph. Notes become nodes; wikilinks under typed headings become directed edges with semantic types. Queryable via networkx — neighbours, centrality, paths, edge distribution, orphan detection.

**Phase 2 — Local semantic search** (`vault_embed.py`, `vault_search.py`)
Embeds note summaries with `BAAI/bge-small-en-v1.5` (384-dim, ~33MB, fully offline). Stored in `sqlite-vec`. Vocabulary-agnostic retrieval over summaries.

**Phase 3 — Graph self-analysis** (`vault_connect_suggest.py`)
Surfaces missing connections: orphan rescue, missing bidirectional edges, tag-cluster gaps, force-fit re-typing candidates. Triage list, not action list.

**Phase 4 — MCP servers**

*Milestone 1* — `vault_search` exposed via MCP.

*Milestone 2* — `graph_expand`, `audit_taxonomy`. Edge weights driven by `vault_taxonomy.yaml`.

*Milestone 3* — `get_note_with_context`, `assemble_context` (vector seed + 1-hop expansion + composite ranking).

*Milestone 3.5* — **PPR upgrade.** Replaces 1-hop expansion with edge-type-aware Personalized PageRank seeded by dense-retrieval scores. Adds intent-aware path attribution (`reasoning_path` field on top-15 results) using semantic-density Dijkstra over inverted taxonomy weights. Adds `mode="standard"|"sparring"` to gate `contradicts` edges in/out of the walk. Cheap usage instrumentation (`note_hits` table) accumulates query→note co-occurrence data for future TERAG-style soft priors.

*Milestone 3.6* — **Perplexity research MCP.** Separate package (`perplexitymcp/`) calling Perplexity Deep Research. Two tools (`research_note`, `apply_research`) with strict provenance discipline — findings go into clearly-marked `## External research (Perplexity, YYYY-MM-DD)` sections, never overwriting existing prose. Vault cross-link auto-matching via fuzzy title resolution. Sidecar SQLite log tracks per-note research history for cost-aware re-call decisions.

---

## MCP Tool Reference

### `mini-vinny`

| Tool | Purpose |
|---|---|
| `vault_search(query, top_k)` | Pure semantic search over note summaries. Cosine similarity ranking. |
| `graph_expand(note_id, max_hops)` | Typed graph traversal from a note. Returns neighbours sorted by edge weight. |
| `audit_taxonomy(check_type, against_type)` | Score every edge of `check_type` by cosine similarity to `against_type`'s description. Returns ranked retype candidates. |
| `get_note_with_context(note_id)` | Full markdown content + immediate typed edge list. Tier-3 retrieval. |
| `assemble_context(query, seed_k, char_budget, mode)` | Hybrid pipeline. Vector seed → PPR walk over typed graph → semantic-path attribution → char-budget-capped context. `mode="sparring"` includes `contradicts` edges. |

### `perplexity-research`

| Tool | Purpose |
|---|---|
| `research_note(note_id, mode, cluster_hops)` | Call Perplexity Deep Research on a note. Returns structured findings with vault cross-link auto-matching. **Does not modify the note.** |
| `apply_research(note_id, sources, claim_checks, cross_links, open_questions, raw_summary, include_raw_summary, researched_at)` | Append selected findings to the note as a marked section. Original prose untouched. |

---

## Slash Commands

Lives at `~/.claude/commands/`. Each is a self-contained micro-prompt that encodes the right tool sequence per intent.

| Command | What it does |
|---|---|
| `/about <note-id>` | Explain a note. PPR biased toward `builds-on`, `exemplifies`, `operationalises`. |
| `/challenge <note-id>` | Pressure-test. PPR in `sparring` mode, prioritises `contradicts`/`challenges`. |
| `/ops <note-id>` | Operationalise. Biased toward worked examples and concrete steps. |
| `/analogies <note-id>` | Cross-domain analogies via `analogous-to` edges. |
| `/paths <id1> <id2>` | Show the shortest semantic chain between two notes. |
| `/research <note-id>` | Perplexity Deep Research with cost guard, compact menu, selective apply. |
| `/audit-edges <type1> <type2>` | Run `audit_taxonomy`, present top retype candidates. |

---

## Edge Taxonomy

Defined in `vault_taxonomy.yaml` — the single source of truth for edge types, weights, and collapse rules. Edit the YAML to add or modify types; no code changes required.

| Type | Weight | Meaning |
|------|--------|---------|
| `builds-on` | 1.5 | A logically depends on B |
| `builds-toward` | 1.5 | Reverse of builds-on (collapsed at load time) |
| `analogous-to` | 1.3 | Same structure across different domains |
| `contradicts` | 1.2 | Substantive incompatible claims |
| `exemplifies` | 0.85 | A is a concrete domain instance of abstract principle B |
| `operationalises` | 0.85 | A is how B becomes practice |
| `challenges` | 0.80 | A complicates B without full contradiction |
| `referenced-in` | 0.8 | Note appears in a map (structural, not semantic) |
| `untyped` | 0.6 | Not yet classified |
| `mentioned` | 0.3 | Name-dropped without relationship |

Weights act as **transition probabilities** in the PPR walk. High-weight semantic edges propagate relevance; low-weight structural edges contribute less. The taxonomy IS the epistemic prior on what kinds of relationships should carry attention.

---

## How retrieval works (first principles)

`assemble_context` runs a four-stage pipeline:

1. **Vector seed.** Encode the query with BGE-small. Cosine-similarity-rank against all note summaries in `sqlite-vec`. Take top `seed_k` as the personalization vector.

2. **Personalized PageRank walk.** Build a weighted DiGraph from the typed graph using taxonomy weights as edge weights. In `standard` mode, drop `contradicts` edges from the walk. Run PPR with `α=0.85` and the seed scores as personalization. The stationary distribution captures both proximity-to-seeds and structural importance in one pass — replacing the hand-tuned 60/40 split of the older composite ranker.

3. **Semantic path attribution.** For top-15 PPR-ranked nodes, run single-source Dijkstra from each seed using **inverted taxonomy weights as edge costs** (so high-weight semantic edges become cheap to traverse). Structural edges (`referenced-in`, `untyped`, `mentioned`) are excluded entirely. The result: each retrieved note carries a `reasoning_path` showing how it connects back to a seed via typed edges. The LLM can narrate it as logic instead of as graph plumbing.

4. **Char-budget cap + instrumentation.** Read full content top-down until the char budget exhausts. Append a row per surfaced note to `note_hits` for future relevance learning. Return the result.

---

## Setup

**Requirements**
- Python 3.11+
- Conda recommended for environment management

**Install**
```bash
git clone https://github.com/vinaldo7-design/KBAI-second-brain.git
cd KBAI-second-brain

conda create -n minivinnymcp python=3.11 -y
conda activate minivinnymcp

pip install -r requirements.txt
pip install -r minivinnymcp/requirements.txt
pip install -r perplexitymcp/requirements.txt
```

**Point at your own vault**
```bash
export VAULT_ROOT="/path/to/your/obsidian/vault"

python vault_graph.py $VAULT_ROOT      # Build typed graph
python vault_embed.py $VAULT_ROOT      # Build vector index
python vault_search.py "your query"    # Test semantic search
```

**Note structure required** — typed links section with headings matching `vault_taxonomy.yaml`:

```markdown
## Links

### Builds on
- [[another-note]] — annotation

### Contradicts
- [[opposing-note]] — why it opposes
```

**Wire up Claude Desktop**
```bash
# Test the suite
pytest minivinnymcp/tests/ perplexitymcp/tests/ -v

# Edit the snippets with your Python path + vault path
# minivinnymcp/claude_desktop_config_snippet.json
# perplexitymcp/claude_desktop_config_snippet.json   (also: PERPLEXITY_API_KEY)

# Merge into ~/Library/Application Support/Claude/claude_desktop_config.json
# Restart Claude Desktop — both servers appear under connectors
```

**Slash commands** ship at `~/.claude/commands/`. Reload Claude Code to pick them up.

---

## Repository Structure

```
.
├── vault_graph.py              # Vault parser → typed JSON graph
├── vault_graph_loader.py       # networkx query layer + ppr_expand + path_attributions
├── vault_connect_suggest.py    # Graph self-analysis + connection suggestions
├── vault_embed.py              # Summary embedder (BGE-small → sqlite-vec)
├── vault_search.py             # Semantic search CLI
├── vault_taxonomy.yaml         # Edge type definitions (single source of truth)
├── requirements.txt
│
├── minivinnymcp/               # Vault retrieval MCP
│   ├── server.py               # 5 tools: search, expand, audit, get_note, assemble
│   ├── requirements.txt
│   ├── claude_desktop_config_snippet.json
│   └── tests/
│       ├── test_vault_search.py
│       └── test_graph_tools.py        # 27 tests covering PPR, paths, instrumentation
│
└── perplexitymcp/              # External research MCP
    ├── server.py               # 2 tools: research_note, apply_research
    ├── requirements.txt
    ├── claude_desktop_config_snippet.json
    └── tests/
        └── test_perplexity.py         # 21 tests with mocked API
```

---

## Stack

- **Graph:** `networkx` over `vault-graph.json` (taxonomy-weighted DiGraph)
- **Vector search:** `sqlite-vec` + `sentence-transformers` (`BAAI/bge-small-en-v1.5`, 384-dim)
- **MCP servers:** `mcp` Python SDK (FastMCP pattern)
- **PPR:** `nx.pagerank` with personalization vector + edge weight gating
- **External research:** Perplexity Sonar Deep Research API
- **LLM:** Anthropic Claude (Sonnet 4.6) via Claude Desktop
- **Vault:** Obsidian (markdown + wikilinks)

---

## Status

- ✅ Phase 1 — Typed graph parser + query layer
- ✅ Phase 2 — Local semantic search (sqlite-vec + BGE-small)
- ✅ Phase 3 — Graph self-analysis (vault_connect_suggest.py)
- ✅ Phase 4 Milestone 1 — `vault_search` MCP tool
- ✅ Phase 4 Milestone 2 — `graph_expand` + `audit_taxonomy`
- ✅ Phase 4 Milestone 3 — `get_note_with_context` + `assemble_context`
- ✅ Phase 4 Milestone 3.5 — PPR retrieval + path attribution + `note_hits` instrumentation
- ✅ Phase 4 Milestone 3.6 — Perplexity research MCP server (`research_note`, `apply_research`)
- ✅ Slash command suite + CLAUDE.md tool discipline section
- 🔨 Phase 4 Milestone 4 — Voice prior + auto-routing for non-slash queries
- 📋 Phase 5 candidates — TERAG soft-prior from `note_hits`, Perplexity cluster mode, AGRAG cost-penalised subgraph selection

---

## Licence

MIT
