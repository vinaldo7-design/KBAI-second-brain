# Mini Vinny / KBAI

A personal AI knowledge agent over an Obsidian vault. Four agent roles, one
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

On top of the vault sit four agents with clean scopes:

| Role | Owns |
|---|---|
| **Mini Vinny** | Vault retrieval, graph reasoning, cognitive routing |
| **Write Agent** | The only mutator — every vault write is journaled |
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

- **22 slash commands** live.
- MCP tools across two servers (mini-vinny, write-agent stub).
- **164 tests** passing.
- Stages 0, 1, 2, 4, 5, 5.5, 5.6, 9 shipped. Stage 3 (Write Agent live
  mutations) deferred until usage demand surfaces. Stage 6/7/8
  (eval harness + calibration) blocked on accumulated `council_events`
  data — accumulating organically as the system is used.

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

### Slash commands

Symlink the versioned commands and voices into your home `~/.claude/`:

```bash
ln -s "$PWD/claude/commands" ~/.claude/commands
ln -s "$PWD/claude/voices"   ~/.claude/voices
```

---

## Slash commands

22 total, organised by intent.

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

### Maintenance

| Command | What it does |
|---|---|
| `/audit-edges <type1> <type2>` | Triage edges that may be the wrong type |
| `/connect <fuzzy>` | Suggest new typed links |
| `/capture <text>` | Quick idea capture (preview-only until Stage 3) |

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
claim to model a mind. Until calibration (Stage 8) earns one from real
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
| `vinay` | Reserved — pulls live from notes tagged `voice-exemplar: true` |

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
│   ├── embed/                    # Reindex hooks
│   ├── eval/                     # Eval scaffolding + sampler
│   ├── graph/                    # Reindex hooks
│   ├── instrumentation/          # note_hits, council_events logs
│   ├── retrieve/                 # dense, ppr, path, assembler
│   ├── storage/                  # note_io, note_resolver
│   ├── voice_profile/            # Voice exemplar hashing + cache
│   └── contracts.py              # Pydantic models for all boundaries
│
├── minivinnymcp/                 # Mini Vinny MCP server (read-only)
├── writeagentmcp/                # Write Agent (stub-only until Stage 3)
│
├── claude/
│   ├── commands/                 # 22 slash commands (mirrored to ~/.claude/)
│   └── voices/                   # 4 voice archetypes
│
├── docs/
│   ├── refactor-plan.md          # Master plan with stage checkboxes
│   ├── operating-manual.md       # User guide for daily use
│   └── stage0-notes.md           # Stage 0 retrospective
│
├── eval/                         # Golden-set queries (drafts)
├── scripts/                      # Pre-push hooks
│
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

`assemble_context` (now decomposed into `kbai/retrieve/{dense,ppr,path,
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
profile calibration (Stage 8) possible.

### Single-writer invariant

Mini Vinny contains no file-write code. The Write Agent is
the only mutator and journals every change. Currently in stub mode;
Stage 3 turns on real mutations when usage demands it.

### Two fidelity axes

Voice changes how an answer reads. Cognitive profiles change what is
retrieved. They never overlap.

---

## Testing

```bash
PYTEST=/path/to/.venv/bin/pytest

# Full suite
$PYTEST minivinnymcp/tests/ writeagentmcp/tests/ -q
```

Test taxonomy spans:

- L1 unit (single module, no I/O)
- L2 integration (module ↔ storage adapter)
- L3 contract (MCP adapter → tool result schema validates against
  `kbai/contracts.py` Pydantic models)
- L4 retrieval eval (planned for Stage 6)

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
