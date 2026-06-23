# Mini Vinny / KBAI

A personal AI knowledge agent over an Obsidian vault. Three agent roles, one
typed graph, two fidelity axes (voice and **thinking**). Designed to make
me think with my own writing as the prior — not to be a chatbot, not a RAG
demo.

Built by [@vinaynair](https://github.com/vinaynair). Local-first.
Privacy-preserving where possible. Opinionated about boundaries.

---

## What it is

The vault is the substrate. Notes are markdown with YAML frontmatter and
typed wikilinks (`builds-on`, `contradicts`, `analogous-to`, `exemplifies`,
`challenges`, `operationalises`, plus structural `referenced-in`, `untyped`,
`mentioned`). The graph IS the vocabulary; structured links are how meaning
travels.

On top of the vault sit three agents with clean scopes:

| Role | Owns |
|---|---|
| **Mini Vinny** | Vault retrieval, graph reasoning, cognitive routing — **read-only** |
| **Write Agent** | The only mutator — every vault write is journaled. **Live.** |
| **Claude** | Orchestration, voice rendering, human-in-the-loop gates |

Two independent fidelity axes layer on top:

- **Voice fidelity** (rendering) — same content, different expression.
- **Thinking fidelity** (retrieval) — same graph, different traversal.
  Five functional cognitive profiles: `default`, `explorer`, `operator`,
  `builder`, `skeptic`, plus `exhaustive` for deep audits.

The flagship feature is **Council Mode** — running the same query through
three profiles in parallel (explorer + operator + skeptic), then
synthesizing with consensus / disagreement structure made explicit.

---

## Status

- **21 slash commands** live.
- MCP tools across two servers: **mini-vinny** (16 read-only tools) and
  **write-agent** (3 live, journaled mutators).
- **316 tests** passing.
- The Write Agent is **live**: real journaled mutations (`write_create_note`,
  `write_append_research_section`, `write_apply_link_suggestions`), each body
  ≤5 lines delegating into `kbai/storage/`.
- Frontmatter is structurally enforced on write. Deferred-tool discovery and
  embed-on-write freshness are in place.
- Eval harness + profile calibration remain blocked on accumulated
  `council_events` data — accumulating organically as the system is used.

See [`docs/refactor-plan.md`](docs/refactor-plan.md) for the full stage
plan and verification stamps.

---

## Quick start

Requires Python 3.10+ and an Obsidian vault.

```bash
git clone https://github.com/vinaldo7-design/KBAI-second-brain.git
cd KBAI-second-brain

python -m venv .venv && source .venv/bin/activate
pip install -r minivinnymcp/requirements.txt
pip install -r writeagentmcp/requirements.txt
pip install pydantic pytest

# Build the typed graph from your vault
python vault_graph.py /path/to/vault

# Build the embedding index
python vault_embed.py

# Run the test suite
VAULT_ROOT=/path/to/vault pytest \
  minivinnymcp/tests/ writeagentmcp/tests/ -q
```

### Wiring into Claude Desktop

Two MCP servers, configured in
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```jsonc
{
  "mcpServers": {
    "mini-vinny": {
      "command": "/path/to/python",
      "args": ["-m", "minivinnymcp.server"],
      "env": { "VAULT_ROOT": "/path/to/vault" }
    },
    "write-agent": {
      "command": "/path/to/python",
      "args": ["-m", "writeagentmcp.server"],
      "env": { "VAULT_ROOT": "/path/to/vault" }
    }
  }
}
```

Snippets in each server's `claude_desktop_config_snippet.json`. Restart
Claude Desktop after edits — MCP tool list is cached at process start.

### Slash commands and voices

`~/.claude/commands/` and `~/.claude/voices/` are canonical — that is where
Claude Desktop reads them at runtime. The copies under `claude/` in this repo
are a versioned **snapshot** for portfolio and review purposes, not a live
symlink. To use them, copy (or sync) the contents into your home `~/.claude/`:

```bash
cp claude/commands/*.md ~/.claude/commands/
cp claude/voices/*.md   ~/.claude/voices/
```

---

## Slash commands

21 total, organised by intent.

### Discovery

| Command | What it does |
|---|---|
| `/find <fuzzy>` | Semantic search; returns top-5 candidates with summaries |
| `/recent [N]` | Last N notes by modified time (default 10) |
| `/today` | Notes touched today |
| `/touched <topic>` | Recent notes filtered by topic |
| `/morning` | Daily orientation: recent + a /council suggestion *(experimental)* |

### Read / explain

| Command | What it does |
|---|---|
| `/about <fuzzy>` | Explain a note + its graph connections |
| `/analogies <fuzzy>` | Cross-domain parallels |
| `/ops <fuzzy>` | Operational how-to from a principle note |
| `/paths <id1> <id2>` | Show how two notes connect through the graph |

### Pressure-test / sparring

| Command | What it does |
|---|---|
| `/challenge <fuzzy>` | Counterarguments via skeptic-mode retrieval |
| `/council <query>` | 3 cognitive profiles + synthesizer; flagship |
| `/compare-thinkers <p1>+<p2> <query>` | Side-by-side multi-profile compare |
| `/pressure-test <fuzzy>` | Auto-escalates challenge → council |

### Generative

| Command | What it does |
|---|---|
| `/imagine <fuzzy>` | Propose new research domains from cluster shape (extend / fracture / bridge / deepen / historicise) |

### Maintenance

| Command | What it does |
|---|---|
| `/audit` | Read-only vault health audit (link health, missing connections) |
| `/audit-edges <type1> <type2>` | Triage edges that may be the wrong type |
| `/connect <fuzzy>` | Suggest new typed links (preview only) |
| `/capture <text>` | Idea capture — preview, then write on confirmation |

### Voice / routing

| Command | What it does |
|---|---|
| `/voice <name> <query>` | Apply a voice (orthogonal to retrieval) |
| `/voices` | List available voices |
| `/ask <query>` | Deterministic intent router |

Detailed user guide: [`docs/operating-manual.md`](docs/operating-manual.md).

---

## Cognitive profiles (thinking fidelity)

Same graph, different traversal. Edge weights and policies in
`kbai/cognitive_routing/profiles/*.yaml`.

| Profile | Boosts | Use for |
|---|---|---|
| `default` | (none) | Balanced retrieval |
| `explorer` | `analogous-to`, `exemplifies` | Cross-domain parallels |
| `operator` | `operationalises`, `exemplifies` | Concrete how-to |
| `builder` | `builds-on`, `builds-toward` | Genealogy, lineage |
| `skeptic` | `contradicts`, `challenges` | Counterarguments |
| `exhaustive` | (admits `mentioned`) | Deep audits |

**No person-named profiles in v1.** A profile named after a person is a
claim to model a mind. Until calibration earns one from real
`council_events` data, only functional lenses ship.

---

## Voice library

Modular and combinable via `+`.

| Voice | Style |
|---|---|
| `naval` | Aphoristic compression |
| `tharoor` | Long erudite argument |
| `bourdain` | Vernacular observation |
| `clarkson` | Hyperbolic provocation |

`/voice naval+bourdain explain X` picks dimensions from each rather than
mechanically merging.

---

## Repository layout

```
.
├── kbai/                         # Core library (importable)
│   ├── analytics/                # Connect-suggest read functions
│   ├── cognitive_routing/        # Profiles, registry, applier
│   │   └── profiles/             # YAML profile definitions
│   ├── council/                  # Council Mode retrieval + overlap
│   ├── embed/                    # Reindex hooks + embed-on-write indexer
│   │   └── indexer.py            # Embeds new notes on write (immediate freshness)
│   ├── eval/                     # Eval scaffolding + sampler
│   ├── graph/                    # Reindex hooks
│   ├── imagination/              # Imagine-mode cluster reading
│   ├── instrumentation/          # note_hits, council_events logs
│   ├── retrieve/                 # dense, ppr, path, assembler
│   ├── storage/                  # note_io, note_resolver, writers, journal
│   │   └── frontmatter_migrate.py  # Migrate notes to the canonical schema
│   ├── voice_profile/            # Voice exemplar hashing + cache
│   ├── schema.py                 # Canonical frontmatter schema — single source of truth
│   ├── tool_battery.py           # Deferred-tool discovery battery (session-start surfacing)
│   └── contracts.py              # Pydantic models for all boundaries
│
├── minivinnymcp/                 # Mini Vinny MCP server (read-only, 16 tools)
├── writeagentmcp/                # Write Agent MCP server (live, 3 journaled mutators)
│
├── claude/
│   ├── commands/                 # Slash-command snapshot (canonical copy lives in ~/.claude/)
│   └── voices/                   # Voice archetype snapshot
│
├── docs/
│   ├── refactor-plan.md          # Master plan with stage checkboxes
│   ├── operating-manual.md       # User guide for daily use
│   └── stage0-notes.md           # Stage 0 retrospective
│
├── eval/                         # Golden-set queries (drafts)
├── scripts/                      # Pre-push hooks
│
├── CLAUDE.md                     # Single governance doc (static doctrine + operating rules)
├── vault_graph.py                # Vault → typed JSON graph builder
├── vault_graph_loader.py         # NetworkX wrapper, PPR, paths
├── vault_embed.py                # BGE → sqlite-vec indexer
├── vault_search.py               # Embedding search CLI
├── vault_connect_suggest.py      # Thin CLI over kbai/analytics
├── vault_taxonomy.yaml           # Closed edge type set
└── pyproject.toml                # Package metadata (declarative)
```

---

## Architecture highlights

### Personalized PageRank with edge-type-aware weights

`assemble_context` (decomposed into `kbai/retrieve/{dense,ppr,path,
assembler}.py`) runs:

1. Dense vector seed via BGE-small over note summaries.
2. Edge-type-aware Personalized PageRank (α=0.85), seeded by dense scores.
3. Path attribution via Dijkstra over inverted taxonomy weights, so
   high-semantic edges (`builds-on`, `analogous-to`) are preferred over
   structural ones (`referenced-in`).

Cognitive profiles modify the PPR transition matrix via `weight_overrides`
— same algorithm, different walk topology.

### Council Mode

The same query runs through 3 profiles in parallel. Returns
`CouncilEvidence` with consensus / unanimous / unique-to overlap analysis.
Claude synthesizes per the `/council` slash-command rules:

- Consensus first.
- Each lens's unique contribution.
- Skeptic must speak.
- Disagreement called out explicitly.
- A recommendation that names how the debate sharpened it.

Every invocation logs to `council_events` — the dataset that makes future
profile calibration possible.

### Single-writer invariant

Mini Vinny contains no file-write code. The Write Agent is the only mutator
and journals every change. It is **live**: `write_create_note`,
`write_append_research_section`, and `write_apply_link_suggestions` perform
real, journaled mutations, each delegating into
`kbai/storage/{note_creator,research_appender,link_applier,write_journal}`.

### Structurally enforced frontmatter

`kbai/schema.py` is the single source of truth for frontmatter — required
fields, allowed enums (status, type, lens), per-type allowed keys, and the
deprecated-field set. Both the parser (`vault_graph.py`) and the writer
import from it. `write_create_note` **hard-rejects** non-conformant
frontmatter: missing required fields, out-of-enum values, keys not allowed
for the note's type, and unknown keys all fail the write rather than landing
malformed notes in the vault.

### Embed-on-write freshness

`kbai/embed/indexer.py` embeds a note into the vector index at write time,
so a newly created note is searchable immediately — no separate reindex pass
required before it can surface in retrieval.

### Deferred-tool discovery battery

`kbai/tool_battery.py` ensures the MCP tool surface is discovered and
exercised at session start, so deferred/lazy tools are reliably available
rather than missing until first use.

### Two fidelity axes

Voice changes how an answer reads. Cognitive profiles change what is
retrieved. They never overlap.

---

## Testing

```bash
PYTEST=/path/to/.venv/bin/pytest

# Full suite (316 passing)
$PYTEST minivinnymcp/tests/ writeagentmcp/tests/ -q
```

Test taxonomy spans:

- L1 unit (single module, no I/O)
- L2 integration (module ↔ storage adapter)
- L3 contract (MCP adapter → tool result schema validates against
  `kbai/contracts.py` Pydantic models)
- L4 retrieval eval (blocked on accumulated `council_events` data)

Pre-push eval hook stub at `scripts/pre-push-eval.sh`. GitHub Actions
workflow stub at `.github/workflows/retrieval-eval.yml`.

---

## What this is not

- Not a chatbot. The system is designed to make you disagree with yourself.
- Not a RAG demo. Retrieval is graph-shaped, typed, and lensed by
  cognitive profile.
- Not a productivity tool. No tasks, no kanban, no calendar. Just
  thinking with your own notes as the prior.
- Not finished. The architecture is. The calibration isn't — that's a
  function of usage time, not code.

---

## Companion writing

Substack essay series on architectural restraint, AI governance, and
building minimum capable systems. The vault is the staging ground; the
essays are the published artefacts.

---

## License

MIT.
