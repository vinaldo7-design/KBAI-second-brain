"""Stage 1 item 1.3: unified note-file resolution.

Before this module, mini-vinny and perplexity each had their own _find_note_file
with subtly different fallback logic. This unifies them. Both servers now
import from here.

Resolution order:
  1. If `note_id` looks like a path (contains "/" or ends with ".md"), try it.
  2. If a graph `node` dict is provided, try its filepath/file_path/path keys.
  3. Fall back to a vault-wide rglob for `<note_id>.md`.

Returns the first match or None.
"""

from __future__ import annotations

from pathlib import Path


def find_note_file(
    note_id: str,
    vault_root: Path,
    node: dict | None = None,
) -> Path | None:
    if not note_id:
        return None
    vault_root = Path(vault_root)

    # 1. note_id-as-path
    if "/" in note_id or note_id.endswith(".md"):
        candidate = (
            Path(note_id)
            if Path(note_id).is_absolute()
            else vault_root / note_id
        )
        if candidate.exists():
            return candidate

    # 2. graph metadata hints
    if node:
        for key in ("filepath", "file_path", "path"):
            fp = node.get(key)
            if fp:
                p = vault_root / fp
                if p.exists():
                    return p

    # 3. vault-wide search
    for p in vault_root.rglob(f"{note_id}.md"):
        return p
    return None
