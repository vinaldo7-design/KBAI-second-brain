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

`make` lists everything. The ones you need:

| Command | What it does |
|---|---|
| `make install` | Set up the environment and the pre-push check |
| `make verify` | Rebuild the graph and index, then run every check |
| `make test-fast` | Tests that need no vault or ML; this is what CI runs |
| `make links FILE=<file>` | Apply a reviewed list of links; add `DRY=1` to preview |
| `make ingest M=<module>` | Push reviewed lecture notes |
| `make notes-snapshot` | Save the notes to their private history |

Restart Claude Desktop after changing server code.

## Applying links in bulk

Give `make links` a JSON list. Reasons are kept on the link, and `contradicts`, `analogous-to` and the builds pair get their mirror line automatically. One bad entry stops the whole batch.

```json
[{"source": "note-a", "target": "note-b", "type": "contradicts", "why": "the question they disagree on"}]
```

## Note history

Notes are git-ignored in this public repo. Their history is a separate private repo at `~/.local/share/kbai/notes.git`, with no remote. To see or recover a note:

```bash
git --git-dir="$HOME/.local/share/kbai/notes.git" log --oneline -- 01-Ideas/some-note.md
git --git-dir="$HOME/.local/share/kbai/notes.git" show <commit>:01-Ideas/some-note.md
```
