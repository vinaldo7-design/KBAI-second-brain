"""Canonical body skeletons — one per note type.

`BODY_SKELETON` is loaded from `kbai/templates/*.md` at module init. Each
skeleton file is a full canonical-shape note (frontmatter + body); only the
body portion is exposed here. The frontmatter is preserved on disk because
the regen script (Phase 6c) derives `Templates/*.md` Obsidian Templater files
from these skeletons.

`render_body(note_type, *, title, summary)` substitutes the two placeholders
`{title}` and `{summary}` via plain str.replace — never str.format — so any
stray curly braces (e.g. inside dataview blocks) pass through verbatim.

Drift invariants enforced by tests:
  - skeleton file set == kbai.schema.ALLOWED_TYPES
  - every link section heading ⊆ EDGE_HEADING values from vault_taxonomy.yaml
  - every skeleton's default status ∈ ALLOWED_STATUSES
  - every skeleton's lifecycle_stage (if present) ∈ ALLOWED_LIFECYCLE_STAGES
"""

from __future__ import annotations

from pathlib import Path


_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _extract_body(text: str) -> str:
    """Return everything after the closing `---\\n` of the frontmatter block,
    stripped of leading blank lines."""
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError("template file missing frontmatter delimiters")
    return parts[2].lstrip("\n")


def _load_skeletons() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(_TEMPLATES_DIR.glob("*.md")):
        out[path.stem] = _extract_body(path.read_text(encoding="utf-8"))
    return out


BODY_SKELETON: dict[str, str] = _load_skeletons()


def render_body(note_type: str, *, title: str, summary: str) -> str:
    """Render the canonical body for a note of the given type.

    Raises KeyError if note_type has no skeleton — by contract the caller
    has already validated `note_type` ∈ ALLOWED_TYPES.
    """
    if note_type not in BODY_SKELETON:
        raise KeyError(
            f"no skeleton for note_type {note_type!r}; "
            f"known: {sorted(BODY_SKELETON)}"
        )
    return (
        BODY_SKELETON[note_type]
        .replace("{title}", title)
        .replace("{summary}", summary)
    )
