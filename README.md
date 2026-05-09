# Mini Vinny

A personal AI knowledge agent built on top of an Obsidian second brain. Combines a typed knowledge graph with local semantic search to power retrieval-augmented synthesis via Claude.

Built by [@vinaynair](https://github.com/vinaynair). Companion to the [Substack](https://substack.com) essay series on AI governance, architectural restraint, and building minimum capable systems.

---

## What It Does

The vault is an Obsidian knowledge graph — atomic notes connected by typed edges encoding semantic relationships. Mini Vinny is the AI layer on top: it retrieves structurally coherent context from the graph and passes it to Claude for synthesis, sparring, and essay drafting.

Four phases:

**Phase 1 — Typed graph parser** (`vault_graph.py`, `vault_graph_loader.py`)
Parses Obsidian markdown into a typed JSON graph. Notes become nodes; wikilinks under typed headings become directed edges with semantic types. Queryable via networkx — neighbours, centrality, paths, edge distribution, orphan detection.

**Phase 2 — Semantic search** (`vault_embed.py`, `vault_search.py`)
Embeds note summaries using `BAAI/bge-small-en-v1.5` (384d, ~33MB, fully offline) stored in `sqlite-vec`. Finds notes by meaning, not keyword — vocabulary-agnostic retrieval over summaries.

**Phase 3 — Graph self-analysis** (`vault_connect_suggest.py`)
Analyses the graph structure and suggests missing connections: orphan rescue, missing bidirectional edges, tag-cluster gaps, force-fit re-typing candidates. Output is a triage list, not an action list — ~50% acceptance rate on first pass.

**Phase 4 — MCP server** (`minivinnymcp/`)
Exposes retrieval tools to Claude Desktop via the Model Context Protocol. Hybrid pipeline: vector seeds → 1-hop typed graph expansion → combined ranking → token-budget-capped context assembly. Edge weights driven by `vault_taxonomy.yaml`.

---

## Architecture Decisions

| Fork | Decision |
|------|----------|
| LLM | Claude API — Sonnet 4.6 |
| Voice prior | Layered system prompt (style rules + exemplars, cached); `voice-exemplar: true` tag for dynamic retrieval |
| Retrieval | Hybrid: vector seed (sqlite-vec) → 1-hop graph expansion (networkx) → composite ranking |
| Interface | MCP server for Claude Desktop; CLI for testing |
| Memory | Stateless — vault is the memory layer |

---

## Edge Taxonomy

Defined in `vault_taxonomy.yaml` — the single source of truth for edge types, weights, and collapse rules. Edit the YAML to add or modify types; no code changes required.

| Type | Weight | Meaning |
|------|--------|---------|
| `builds-on` | 0.9 | A logically or epistemically depends on B |
| `builds-toward` | 0.9 | Reverse of builds-on (collapsed to reversed builds-on in graph loader) |
| `contradicts` | 1.0 | Genuine intellectual opposition |
| `challenges` | 0.8 | Soft tension — A complicates B without full contradiction |
| `exemplifies` | 0.85 | A is a concrete domain instance of abstract principle B |
| `operationalises` | 0.85 | A is how B becomes practice |
| `analogous-to` | 0.7 | Peer-level structural homology |
| `referenced-in` | 0.4 | Administrative — note appears in a map |

`contradicts` edges are elevated in retrieval priority on synthesis tasks — they prevent the agent from being a yes-machine.

---

## Setup

**Requirements**
- Python 3.11+
- Conda recommended for environment management

**Install**
```bash
# Clone
git clone https://github.com/vinaynair/mini-vinny.git
cd mini-vinny

# Environment
conda create -n minivinnymcp python=3.11 -y
conda activate minivinnymcp

# Dependencies
pip install -r requirements.txt
pip install -r minivinnymcp/requirements.txt
```

**Point at your own vault**
```bash
export VAULT_ROOT="/path/to/your/obsidian/vault"

# Build the graph
python vault_graph.py $VAULT_ROOT

# Build the vector index
python vault_embed.py $VAULT_ROOT

# Test semantic search
python vault_search.py "your query here"
```

**Note structure required**
Notes need a typed links section with headings that match `vault_taxonomy.yaml`. Example:

```markdown
## Links

### Builds on
- [[another-note]] — annotation

### Contradicts
- [[opposing-note]] — why it opposes
```

**Wire up Claude Desktop**
```bash
# Run the test suite
cd minivinnymcp
VAULT_ROOT="/path/to/vault" pytest tests/ -v

# Merge the config snippet
# Edit minivinnymcp/claude_desktop_config_snippet.json with your Python path
# Then merge into ~/Library/Application Support/Claude/claude_desktop_config.json
# Restart Claude Desktop — Mini Vinny appears under connectors
```

---

## Repository Structure

```
mini-vinny/
├── vault_graph.py              # Vault parser → typed JSON graph
├── vault_graph_loader.py       # networkx query layer
├── vault_connect_suggest.py    # Graph self-analysis + connection suggestions
├── vault_embed.py              # Summary embedder (BGE-small → sqlite-vec)
├── vault_search.py             # Semantic search CLI
├── vault_taxonomy.yaml         # Edge type definitions (single source of truth)
├── requirements.txt            # Core dependencies
└── minivinnymcp/               # MCP server for Claude Desktop
    ├── server.py               # FastMCP server, tool definitions
    ├── requirements.txt        # MCP-specific dependencies
    ├── tests/
    │   └── test_vault_search.py
    └── claude_desktop_config_snippet.json
```

---

## Stack

- **Graph:** `networkx` over `vault-graph.json`
- **Vector search:** `sqlite-vec` + `sentence-transformers` (`BAAI/bge-small-en-v1.5`)
- **MCP server:** `mcp` Python SDK (FastMCP pattern)
- **LLM:** Anthropic Claude API (Sonnet 4.6)
- **Vault:** Obsidian (markdown + wikilinks)

---

## Status

- ✅ Phase 1 — Typed graph parser + query layer
- ✅ Phase 2 — Local semantic search (sqlite-vec + BGE-small)
- ✅ Phase 3 — Graph self-analysis (vault_connect_suggest.py)
- ✅ vault_taxonomy.yaml config layer
- 🔨 Phase 4 — MCP server (Milestone 1 shipped: vault_search tool live)

---

## Licence

MIT
