# Phase 6 — body template consolidation

**Status:** planning approved, code not started.
**Context:** sequel to Phases 1–5 (graph_stats audit → loader query-time views → section_patcher yaml-loaded → schema + validator gate → single journalled writer). To resume, the user will say "just do phase 6" or equivalent — this file is the brief.

---

## Goal

Eliminate three sources of body-structure drift:

1. `Templates/*.md` — Obsidian Templater files, read by no Python code in `kbai/`.
2. `~/.claude/commands/capture.md` — `/capture`'s inline body sketch (disagrees with `Templates/idea-note.md`).
3. The empty seat where canonical body assembly should live — `note_creator.py` doesn't assemble bodies today; it concatenates whatever string the caller passes.

Plus two doctrine drifts surfaced by earlier phases:

- Template status vocabulary (`unprocessed`, `processing`, `draft`) contradicts `ALLOWED_STATUSES = {seedling, evergreen}` from `kbai/schema.py` / CLAUDE-static.md §6.
- Template heading text (`### Referenced in Maps`) vs `vault_taxonomy.yaml`'s `section_heading` display casing — cosmetic only, since Phase 3's case-insensitive regex covers correctness, but still doctrine drift.

---

## End state

A code-side canonical body skeleton per note type. The writer renders from it. `/capture` and the Templater files derive from it. Template status defaults aligned to schema. Template heading text aligned to yaml.

---

## Source-of-truth map

| Note type | New SoT | Derivations | Deletions |
|---|---|---|---|
| `idea` | `kbai/templates/idea.md` | `Templates/idea-note.md` (regenerated); `/capture` body when type=idea | — |
| `capture` | `kbai/templates/capture.md` | `Templates/capture-note.md`; `/capture` body when type=capture | — |
| `learning` | `kbai/templates/learning.md` | `Templates/learning-note.md` | — |
| `essay` | `kbai/templates/essay.md` | `Templates/essay-note.md` | — |
| `personal` | `kbai/templates/personal.md` | `Templates/personal-note.md` | — |
| `map` | `kbai/templates/map.md` | `Templates/map-note.md` | — |
| `concept` | `kbai/templates/concept.md` | (no current Templater file) | — |
| `quick-capture` | — | — | `Templates/quick-capture.md` *(decision point — see below)* |

**Format choice**: markdown skeletons in `kbai/templates/` (not Python literals in `kbai/templates.py`). Visual review parity with vault notes.

---

## File-by-file changes

### New
- `kbai/templates/` directory — one `.md` per `ALLOWED_TYPES` entry. Frontmatter contains only user-supplied fields (`title`, `type`, `status`, `summary`, `tags`) with `{title}` / `{summary}` placeholders. Status defaults sourced from `ALLOWED_STATUSES`. Link section headings emitted via `EDGE_HEADING` (yaml-derived).
- `kbai/templates.py` — exports `BODY_SKELETON: dict[str, str]` (loaded from `kbai/templates/*.md` at module init) and `render_body(note_type: str, *, title: str, summary: str) -> str`. Drift detector: `BODY_SKELETON.keys() == ALLOWED_TYPES`.
- `scripts/regenerate_obsidian_templates.py` — reads canonical skeletons, substitutes Python `{title}` → Templater `{{title}}` and adds `{{date:YYYYMMDDHHmm}}` for `id` / `{{date:YYYY-MM-DD}}` for `created`/`updated`, writes `Templates/<type>-note.md`. ~30 lines. Idempotent.

### Modified
- `kbai/storage/note_creator.py` — when `body == ""` and `frontmatter["type"]` is set, call `render_body(...)`. Backward-compatible: non-empty `body` still flows through verbatim.
- `~/.claude/commands/capture.md` — drop the inline body sketch. The slash command builds only the frontmatter dict and passes `body=""`; the writer takes over body assembly.
- `Templates/*.md` — regenerated outputs. Add a header comment `<!-- generated from kbai/templates/<type>.md — do not edit by hand -->`.
- `CLAUDE-static.md` §4 — templates table: rename "Template" column to "Canonical skeleton" pointing at `kbai/templates/`. Footnote: `Templates/*.md` are derived files.

### Possibly deleted (decision pending)
- `Templates/quick-capture.md` — its `type:` field is `capture`, identical to capture-note.md. No semantic distinction in code.

### Untouched (already SoT-aligned from earlier phases)
- `vault_taxonomy.yaml`, `kbai/schema.py`, `kbai/storage/section_patcher.py`, `kbai/storage/research_appender.py`, `perplexitymcp/server.py`.

---

## Migration order

Each sub-phase ends in a working system.

**6a — code-side canonical, writer wired**
1. Add `kbai/templates/` + skeleton files.
2. Add `kbai/templates.py` with `BODY_SKELETON` + `render_body()`.
3. Wire `render_body` into `note_creator.create_note` (empty-body branch only).
4. Tests:
   - Drift detector: skeleton file set equals `ALLOWED_TYPES` (Phase 3 pattern).
   - Every link heading in every skeleton matches a value in `EDGE_HEADING`.
   - Every skeleton's default `status` is in `ALLOWED_STATUSES`.
   - `render_body("idea", title="T", summary="S")` includes every link section.
   - `create_note(..., body="")` produces a file containing the rendered skeleton.

**6b — `/capture` pruned**
1. Strip the hardcoded body sketch from `~/.claude/commands/capture.md`.
2. Manual smoke: run `/capture <idea>` and inspect the resulting note.

**6c — Obsidian Templater files regenerated**
1. Add `scripts/regenerate_obsidian_templates.py`.
2. Run once. Commit the regenerated `Templates/*.md`.
3. (Optional) pre-commit hook so `Templates/` cannot drift from `kbai/templates/`.

**6d — quick-capture decision applied** (deferrable)

---

## Vault notes needing heading backfill

Phase 3's case-insensitive regex means **no backfill is required for writer correctness**. Existing headings of any casing resolve. The question is cosmetic / grep predictability.

**Audit** (read-only, before deciding): scan every `.md` under `00-Captures/`, `01-Ideas/`, `02-Learning/`, `04-Substack/`, `05-Personal/`, `06-Maps/` for headings whose lowercased form matches a yaml `section_heading` but whose text disagrees with canonical `### {first_letter_upper(yaml_heading)}`. Expected dominant case: `### Referenced in Maps` vs canonical `### Referenced in maps`.

**Three paths**:
1. **No backfill.** Cheapest. Drift visible to grep, not to code.
2. **One-shot rewrite.** Deterministic find-and-replace across the listed folders. Idempotent. Run after `kbai/templates/` is finalized. Cleanest.
3. **Lazy backfill.** Touch headings only when the writer next mutates a note. Mixed state indefinitely.

Recommend (2), executed after 6a–6c land. Strictly out of Phase 6's code scope (it's a vault-content change), but worth listing now.

**Status-value backfill is a separate question.** Existing capture/learning/essay notes have `status: {unprocessed, processing, draft}` from old Templater defaults. Per `ALLOWED_STATUSES` they're technically drift. Three options:
- **Leave as-is.** Validator gates *new* writes only.
- **Map to seedling.** Loses lifecycle information.
- **Extend schema.** Add a `lifecycle_stage` field separate from `status`.

This drives 6d and possibly a Phase 7. Not absorbed into 6.

---

## Risks and tradeoffs

1. **Obsidian Templater coupling** — regen script overwrites hand-edits to `Templates/*.md`. Mitigation: pre-commit hook + `<!-- generated -->` header. Low pain since no Python reads those files today.
2. **Single skeleton per type may be too rigid** — e.g., a `voice-exemplar: true` idea note may want a different skeleton. Ship one per type for now; extend `render_body(type, variant="...")` later if needed.
3. **Quick-capture UX** — if you use Obsidian's template picker and "Quick Capture" matters there, deletion costs that affordance. Easy to preserve.
4. **Status-default doctrine shift** — capture/learning/essay aligning to `seedling` collapses lifecycle distinctions. If those matter to you, surface a `lifecycle_stage` field now rather than papering over.

---

## Decision points required before any 6a code

1. **Skeleton format**: `kbai/templates/*.md` (recommended) or `kbai/templates.py` literals?
2. **Obsidian template sync**: regen script (recommended), hand-sync + CI drift check, or leave Templater files alone forever?
3. **Quick-capture**: (a) delete, (b) keep as Obsidian-only with no kbai counterpart, or (c) keep with a kbai counterpart that aliases to `type: capture`?
4. **Heading backfill**: one-shot rewrite (recommended), defer to lazy, or never?
5. **Lifecycle distinctions** (capture's `unprocessed`, learning's `processing`, essay's `draft`): collapse to `seedling`, or extend schema with a `lifecycle_stage` field?

These five decisions shape everything in 6a–6d. Answer before any code lands.
