"""Frontmatter-SSOT brief Task 3: normalise a note's frontmatter to the confirmed
schema. Frontmatter ONLY — body and the ``## Links`` typed-edge sections are never
touched. Journalled, idempotent (re-running a conformant note is a no-op).

Normalisation rules (the 12 signed-off decisions):
  1  rename ``medium`` -> ``origin`` (drop ``medium`` if ``origin`` already set)
  6,7 remove deprecated keys ``domain``, ``links``
  10 remap off-enum status: processed->evergreen+integrated, processing->
     seedling+processing, draft->seedling+draft (lifecycle_stage set if absent)
  -  coerce ``tags`` from a YAML block-scalar string into a list
  -  reorder to canonical field order

Type reclassification (session-log->learning) and notes needing un-inferrable
fields are handled out-of-band (review queue) — this module only applies the
safe, deterministic transforms above.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from kbai.storage.write_journal import record_mutation

_TOOL = "frontmatter_migrate"

# Canonical emit order: shared core, shared-optional, then per-type extensions.
CANONICAL_ORDER = [
    "id", "title", "created", "updated", "type", "status",
    "lifecycle_stage", "summary", "tags", "origin",
    "author", "context", "published_url", "supersedes",
]

_STATUS_REMAP = {
    "processed": ("evergreen", "integrated"),
    "processing": ("seedling", "processing"),
    "draft": ("seedling", "draft"),
}

_REMOVE_KEYS = ("domain", "links")


def normalize_frontmatter(fm: dict) -> tuple[dict, list[str]]:
    """Return (normalised_fm, changes). Pure — no I/O. Empty ``changes`` means the
    frontmatter was already conformant on every rule this migrator applies."""
    fm = dict(fm)
    changes: list[str] = []

    # 1. medium -> origin
    if "medium" in fm:
        if not fm.get("origin"):
            fm["origin"] = fm.pop("medium")
            changes.append("rename medium->origin")
        else:
            fm.pop("medium")
            changes.append("drop medium (origin already present)")

    # tags: YAML block-scalar string -> list. The block scalar often captured the
    # literal "- " list bullets as text, so strip a leading bullet from each line.
    tags = fm.get("tags")
    if isinstance(tags, str):
        items = []
        for line in tags.replace(",", "\n").splitlines():
            s = line.strip()
            if s.startswith("- "):
                s = s[2:].strip()
            elif s.startswith("-"):
                s = s[1:].strip()
            if s:
                items.append(s)
        fm["tags"] = items
        changes.append(f"coerce tags str->list ({len(items)} items)")

    # 6,7. remove deprecated keys
    for k in _REMOVE_KEYS:
        if k in fm:
            fm.pop(k)
            changes.append(f"remove {k}")

    # 10. status remap
    st = fm.get("status")
    if st in _STATUS_REMAP:
        new_st, ls = _STATUS_REMAP[st]
        fm["status"] = new_st
        if not fm.get("lifecycle_stage"):
            fm["lifecycle_stage"] = ls
        changes.append(f"status {st}->{new_st} + lifecycle_stage={ls}")

    # reorder to canonical order (applied whenever any substantive change fired)
    if changes:
        ordered = {k: fm[k] for k in CANONICAL_ORDER if k in fm}
        for k in fm:  # preserve any unranked keys at the end, original order
            if k not in ordered:
                ordered[k] = fm[k]
        fm = ordered

    return fm, changes


def _split(text: str) -> tuple[dict | None, str]:
    """Return (frontmatter_dict, rest_after_closing_fence). rest preserves the body
    byte-for-byte (including any further '---' in the body)."""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    fm = yaml.safe_load(parts[1])
    return (fm if isinstance(fm, dict) else None), parts[2]


def migrate_note(vault_root, rel_path: str, dryrun: bool = True) -> dict:
    """Read one note, normalise its frontmatter, write it back (unless dryrun).
    Body untouched. Journals the mutation. Returns a result dict; never raises on
    a conformant/no-op note."""
    vault_root = Path(vault_root)
    path = vault_root / rel_path
    note_id = path.stem
    original = path.read_text(encoding="utf-8")
    fm, rest = _split(original)
    if fm is None:
        return {"path": rel_path, "status": "skipped", "reason": "no-frontmatter", "changes": []}

    new_fm, changes = normalize_frontmatter(fm)
    if not changes:
        return {"path": rel_path, "status": "noop", "changes": []}

    new_yaml = yaml.safe_dump(new_fm, sort_keys=False, allow_unicode=True)
    new_content = f"---\n{new_yaml}---{rest}"

    h_before = hashlib.sha256(original.encode("utf-8")).hexdigest()
    h_after = hashlib.sha256(new_content.encode("utf-8")).hexdigest()

    if new_content == original:  # belt-and-suspenders idempotency
        return {"path": rel_path, "status": "noop", "changes": []}

    if dryrun:
        return {"path": rel_path, "status": "would-migrate", "changes": changes,
                "hash_before": h_before, "hash_after": h_after}

    path.write_text(new_content, encoding="utf-8")
    record_mutation(
        vault_root=vault_root, tool=_TOOL, note_id=note_id, file=rel_path,
        hash_before=h_before, hash_after=h_after, status="applied", dryrun=False,
        payload_json=json.dumps({"changes": changes}),
    )
    return {"path": rel_path, "status": "migrated", "changes": changes,
            "hash_before": h_before, "hash_after": h_after}
