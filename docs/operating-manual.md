# Mini Vinny — Operating Manual

Command reference for day-to-day vault use. Commands live in `claude/commands/`, and `~/.claude/commands` is a symlink to that folder.

## Commands

| Command | Arguments | What it does |
|---|---|---|
| `/find <query>` | free text | Vault search, top 5, then wait for a pick |
| `/find recent [N]` | N, default 10 | Most recently modified notes |
| `/find today` | none | Notes modified since midnight |
| `/find touched <topic>` | filename substring | 20 most recent notes matching the topic |
| `/about <note>` | note id or free text | Core argument and vault connections |
| `/ops <note>` | note id or free text | Concrete steps from operationalises and exemplifies edges |
| `/analogies <note>` | note id or free text | Cross-domain parallels from analogous-to edges |
| `/paths <A> <B>` | two notes | Shortest semantic path between them |
| `/challenge <note>` | note id or free text | Strongest objections, the council if contradictions turn up, and an edit checklist |
| `/council <query>` | free text | One paragraph per cognitive profile, then a synthesis |
| `/compare-thinkers <p1>+<p2> <query>` | profiles and query | Side-by-side results with a divergence score |
| `/imagine <note>` | note id | Propose research domains from cluster shape |
| `/audit` | none, `links`, or `edges <t1> <t2>` | Read-only link suggestions or edge-type drift |
| `/capture <idea>` | free text | Preview a note, write on confirmation |
| `/voice <name> <query>` | voice and query | Apply a voice; `<a>+<b>` fuses two; no arguments lists them |

Voices: `naval`, `tharoor`, `bourdain`, `clarkson`.

## Note resolution

Commands that take a note first search for it. A known issue: `/about`, `/ops`, `/analogies`, `/paths`, `/challenge` and `/imagine` treat a higher score as a better match, but `retrieve_search` returns a distance, where lower is closer.

## Cognitive profiles

Used by `/council`, `/compare-thinkers` and `cognition_retrieve_as`: `default`, `skeptic`, `operator`, `builder`, `explorer`, `exhaustive`. Weights are in `kbai/cognitive_routing/profiles/`.

## Running it

- Check everything: `bash scripts/verify_vault.command`
- Restart Claude Desktop after changing server code.
