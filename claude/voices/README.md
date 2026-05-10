# Voice Library

Modular voice system for response styling. Each voice is a markdown file declaring style rules, persona, and exemplars. Invoked via `/voice <name> <query>`.

## How it works

- `/voice naval brief me on governance capital` — apply naval voice for this response
- `/voice naval+bourdain spar with mastery-trap` — fuse two voices for the response
- `/voice vinay draft a paragraph on architectural restraint` — pull from `voice-exemplar: true` notes in the vault

Voice affects **how** I respond. It does not affect retrieval (which tools get called) — that's intent (slash commands) or auto-routing.

## File format

Each voice file has:

1. **Frontmatter:** `voice` (name), `description`, `dimensions` (length, structure, register, persona, density), `combines_well_with`
2. **Style rules:** what the voice does
3. **Anti-patterns:** what the voice never does
4. **Exemplars:** 2-4 short passages illustrating the voice in action

Dimensions act as the combination grammar — when you fuse `naval+bourdain`, I pick which dimensions come from each based on what produces the strongest hybrid.

## Available voices

- `naval` — short, aphoristic, first-principle compression
- `tharoor` — long, argumentative, erudite layered prose
- `bourdain` — vernacular, observational, deeply specific
- `clarkson` — hyperbolic, performative, conversationally bombastic
- `vinay` — your own voice, retrieved live from vault notes tagged `voice-exemplar: true`

## Adding a voice

Drop a new `.md` file in this directory matching the existing format. The slash command will pick it up automatically — no code changes.

## Combination guide

- `naval+bourdain` → aphoristic structure, observer persona, vernacular register
- `tharoor+clarkson` → argumentative scaffold, hyperbolic register
- `naval+tharoor` → compression and erudition (rare, hard to land)
- `vinay+naval` → your voice with extra compression discipline
