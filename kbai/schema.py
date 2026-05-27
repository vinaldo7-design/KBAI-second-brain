"""Canonical frontmatter schema — single source of truth.

Both the parser (vault_graph.py) and the writer (kbai/storage/note_creator.py)
import from here. Downstream code derives every check from these constants —
no hardcoded field names or allowed-value lists.

The schema is governed by CLAUDE-static.md §4 (canonical frontmatter), §5
(locked lens vocabulary), and §6 (note-taking conventions). When that doctrine
changes, change this module — and only this module.
"""

from __future__ import annotations


# Fields that must be present on every note.
REQUIRED_FRONTMATTER: frozenset[str] = frozenset({
    "id", "title", "type", "status", "summary", "tags",
})

# Fields no longer recognised — surfaced as schema drift by the parser.
DEPRECATED_FRONTMATTER: frozenset[str] = frozenset({"domain", "attachments"})

# Status — CLAUDE-static.md §6: "Status: seedling | evergreen only"
ALLOWED_STATUSES: frozenset[str] = frozenset({"seedling", "evergreen"})

# Note types — CLAUDE-static.md §4 (templates table) + §6 (concept).
# `quick-capture` is a template name, not a type value (its template sets
# `type: capture`), so it is not listed here.
ALLOWED_TYPES: frozenset[str] = frozenset({
    "capture", "idea", "learning", "essay", "personal", "map", "concept",
})

# Lens vocabulary — LOCKED, CLAUDE-static.md §5.
ALLOWED_LENSES: frozenset[str] = frozenset({
    "academic", "strategic", "philosophical",
    "personal", "substack", "professional",
})

# Tag prefixes — CLAUDE-static.md §6.
TAG_PREFIX_TOPIC = "topic/"
TAG_PREFIX_LENS = "lens/"

# Field order emitted by the writer. Mirrors the canonical layout in
# CLAUDE-static.md §4 (id/title/created/updated/type/status/summary/tags).
# `_ordered_frontmatter` in note_creator preserves this order; user-supplied
# fields outside this tuple are appended after, preserving insertion order.
CANONICAL_FIELD_ORDER: tuple[str, ...] = (
    "id", "title", "created", "updated",
    "type", "status", "summary", "tags",
)


def validate_frontmatter(fm: dict) -> str | None:
    """Validate a frontmatter dict against the schema.

    Returns None on success, a specific error string on failure. The writer
    converts the string into a WriteReceipt(status="error", reason=...) so
    failures never raise into the MCP boundary.

    Checks (all values sourced from this module — hardcode nothing):
      - `id` present, non-empty, and not equal to `title`
      - every field in REQUIRED_FRONTMATTER present
      - `summary` non-empty
      - `status` ∈ ALLOWED_STATUSES
      - `type` ∈ ALLOWED_TYPES
      - every tag starts with TAG_PREFIX_TOPIC or TAG_PREFIX_LENS
      - every lens suffix (after TAG_PREFIX_LENS) ∈ ALLOWED_LENSES
    """
    if not fm.get("id"):
        return "id missing or empty"
    if "title" in fm and fm.get("title") and fm["id"] == fm["title"]:
        return "id must not equal title"

    missing = REQUIRED_FRONTMATTER - fm.keys()
    if missing:
        return f"required frontmatter fields missing: {sorted(missing)}"

    summary = fm.get("summary")
    if not summary or not str(summary).strip():
        return "summary missing or empty"

    status = fm.get("status")
    if status not in ALLOWED_STATUSES:
        return (
            f"status {status!r} not in allowed set: {sorted(ALLOWED_STATUSES)}"
        )

    note_type = fm.get("type")
    if note_type not in ALLOWED_TYPES:
        return (
            f"type {note_type!r} not in allowed set: {sorted(ALLOWED_TYPES)}"
        )

    tags = fm.get("tags")
    if not isinstance(tags, list):
        return f"tags must be a list, got {type(tags).__name__}"
    for tag in tags:
        if not isinstance(tag, str):
            return f"tag {tag!r} is not a string"
        if tag.startswith(TAG_PREFIX_LENS):
            lens = tag[len(TAG_PREFIX_LENS):]
            if lens not in ALLOWED_LENSES:
                return (
                    f"lens {lens!r} not in allowed vocabulary: "
                    f"{sorted(ALLOWED_LENSES)}"
                )
        elif not tag.startswith(TAG_PREFIX_TOPIC):
            return (
                f"tag {tag!r} must start with "
                f"{TAG_PREFIX_TOPIC!r} or {TAG_PREFIX_LENS!r}"
            )

    return None
