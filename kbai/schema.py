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
    "id", "title", "created", "updated", "type", "status", "summary", "tags",
})

# Fields no longer recognised — surfaced as schema drift by the parser.
DEPRECATED_FRONTMATTER: frozenset[str] = frozenset({"domain", "attachments"})

# Status — CLAUDE-static.md §6: "Status: seedling | evergreen only"
ALLOWED_STATUSES: frozenset[str] = frozenset({"seedling", "evergreen"})

# Lifecycle stage — orthogonal to status. Optional field; carries type-specific
# lifecycle that previously leaked into `status` (capture's `unprocessed`,
# learning's `processing`, essay's `draft`). Phase 6 introduces this to
# preserve those distinctions without collapsing them to seedling.
ALLOWED_LIFECYCLE_STAGES: frozenset[str] = frozenset({
    "unprocessed", "promoted", "discarded",   # capture
    "processing", "integrated",               # learning
    "draft", "published",                     # essay
})

# Note types — CLAUDE-static.md §4 (templates table) + §6 (concept).
# `quick-capture` is a template name, not a type value (its template sets
# `type: capture`), so it is not listed here.
ALLOWED_TYPES: frozenset[str] = frozenset({
    "capture", "idea", "learning", "essay", "personal", "map", "concept", "project",
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
    "type", "status", "lifecycle_stage", "summary", "tags",
    "origin", "author", "context", "published_url", "supersedes",
)

# Provenance vocabulary (CLAUDE doctrine §4 + corpus). The value of `origin`.
ALLOWED_ORIGINS: frozenset[str] = frozenset({
    "conversation", "lecture", "paper", "session", "capture",
})

# Types on which `origin` (provenance) is allowed. concept/map are structural or
# derived and carry no provenance. `capture` is included so the /capture
# command's `origin: conversation` validates (decision 11 + capture-origin sign-off).
ORIGIN_TYPES: frozenset[str] = frozenset({
    "idea", "learning", "project", "personal", "capture",
})

# Optional fields permitted on every type.
SHARED_OPTIONAL: frozenset[str] = frozenset({"lifecycle_stage"})

# Per-type extension fields (beyond shared core + shared-optional + origin).
TYPE_EXTENSIONS: dict[str, frozenset[str]] = {
    "learning": frozenset({"author", "context"}),
    "essay": frozenset({"published_url"}),
    "project": frozenset({"supersedes"}),
}


def allowed_keys(note_type: str) -> frozenset[str]:
    """Complete set of frontmatter keys permitted on a note of this type:
    shared required core + shared-optional + origin (origin-types only) + that
    type's extensions. Any key outside this set is rejected on write — this is
    what stops free-form drift (e.g. `medium`/`author` on the wrong type)."""
    keys = set(REQUIRED_FRONTMATTER) | set(SHARED_OPTIONAL)
    if note_type in ORIGIN_TYPES:
        keys.add("origin")
    keys |= set(TYPE_EXTENSIONS.get(note_type, frozenset()))
    return frozenset(keys)


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
      - `lifecycle_stage` (if present and non-empty) ∈ ALLOWED_LIFECYCLE_STAGES
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
    if not isinstance(summary, str) or not summary.strip():
        return "summary missing, empty, or not a string"

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

    if fm.get("lifecycle_stage") is not None:
        ls = fm["lifecycle_stage"]
        if ls not in ALLOWED_LIFECYCLE_STAGES:
            return (
                f"lifecycle_stage {ls!r} not in allowed set: "
                f"{sorted(ALLOWED_LIFECYCLE_STAGES)}"
            )

    origin = fm.get("origin")
    if origin is not None and str(origin).strip():
        if origin not in ALLOWED_ORIGINS:
            return f"origin {origin!r} not in allowed set: {sorted(ALLOWED_ORIGINS)}"
        if note_type not in ORIGIN_TYPES:
            return (
                f"origin not allowed on type {note_type!r} "
                f"(only {sorted(ORIGIN_TYPES)})"
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

    # Unknown-key rejection (the gate against free-form drift). type is already
    # validated above, so allowed_keys() is well-defined here.
    allowed = allowed_keys(note_type)
    for key in fm:
        if key not in allowed:
            return (
                f"unknown frontmatter key {key!r} not allowed for type "
                f"{note_type!r}; allowed: {sorted(allowed)}"
            )

    return None
