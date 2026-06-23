# Mini Vinny — Operating Manual

Personal command reference for day-to-day vault use.

---

## Personal UX commands (Stage 9)

| Command | Arguments | What it does |
|---|---|---|
| `/find <query>` | free text | Vault search top 5, compact table, wait for pick |
| `/recent [N]` | N = number (default 10) | N most recently modified notes with relative timestamps |
| `/today` | — | All notes modified since midnight today |
| `/touched <topic>` | topic substring | 20 most recent notes whose filename contains topic |
| `/morning` | — | 5 recent notes + summaries + council suggestion *(experimental)* |
| `/pressure-test <note>` | note-id or free text | Sparring challenge + optional council + edit checklist |
| `/connect` | — | Missing-link suggestions in 5 categories, preview only |
| `/capture <idea>` | free text | Draft note proposal with links, no vault write |

---

## Retrieval & reasoning commands

| Command | Arguments | What it does |
|---|---|---|
| `/about <note>` | note-id or free text | Explain note: core argument + vault connections |
| `/challenge <note>` | note-id or free text | Sparring mode: contradicts/challenges edges |
| `/ops <note>` | note-id or free text | Operationalise: concrete steps from operationalises/exemplifies edges |
| `/analogies <note>` | note-id or free text | Cross-domain analogies via analogous-to edges |
| `/paths <A> <B>` | two note-ids or free text | Shortest semantic path between two notes |
| `/council <query>` | free text | Multi-lens council: one paragraph per cognitive profile |
| `/ask <query>` | free text | Intent router: classifies query and calls the right tool sequence |
| `/compare-thinkers <p1>+<p2> <query>` | profiles + query | Side-by-side profile comparison with divergence score |

---

## Audit commands

| Command | Arguments | What it does |
|---|---|---|
| `/audit-edges <type1> <type2>` | two edge types | Find edges that may be mis-typed between the two types |

---

## Voice commands

| Command | Arguments | What it does |
|---|---|---|
| `/voice <name> <query>` | voice name + query | Apply a voice to the response |
| `/voice <a>+<b> <query>` | two voices + query | Fuse two voices creatively |
| `/voices` | — | List available voices |

Available voices: `naval` (aphoristic compression), `tharoor` (long erudite argument), `bourdain` (vernacular observation), `clarkson` (hyperbolic provocation).

---

## Fuzzy resolution

All commands that accept a note-id now include Step 0 fuzzy resolution:

| Tier | Condition | Behaviour |
|---|---|---|
| exact | query is a known note_id | Proceed immediately |
| fuzzy | top search score ≥ 0.7 | Auto-resolve, print `Resolved: [[note_id]] (score X)` |
| ambiguous | 0.4 ≤ top score < 0.7 | Print candidates, ask user to pick |
| no_match | top score < 0.4 | Print error, stop |

Commands with fuzzy resolution: `/about`, `/ops`, `/analogies`, `/paths`, `/challenge`, `/pressure-test`.

---

## Cognitive profiles

Used by `/council`, `/compare-thinkers`, and `cognition_retrieve_as`.

| Profile | Character |
|---|---|
| `default` | Balanced PPR traversal, contradicts suppressed |
| `skeptic` | Contradicts and challenges weighted up, builds-on down |
| `operator` | Operationalises and exemplifies weighted up |
| `builder` | Builds-on and inspires weighted up |
| `exhaustive` | All edge types included (mentioned edges loaded) |

---

## Tool hierarchy

```
Vault (Mini Vinny tools)  >  web
```

For any question about Vinay's own thinking, the vault is authoritative.
