"""Capture-pipeline Task 3 (Part A): incremental embedding-reindex hook — REAL.

Previously a stub. Now, given a note_id (and optionally the vault root), it
locates the note file, reads `summary` from its frontmatter, and embeds it into
the sqlite-vec index via kbai.embed.indexer.embed_note. This closes the
same-session staleness window: a note created through write_create_note is
searchable immediately, without waiting for a full `vault_embed.py` re-embed.

Contract (unchanged): accepts a single note_id (vault_root is an optional
second arg so the existing `update_note_embeddings(note_id)` call site keeps
working — when omitted, the root is resolved from $VAULT_ROOT or this module's
location). MUST NOT call vault_embed.main / rebuild the whole index — it embeds
exactly one note. Never raises: every failure is returned as a status dict so
the write path can swallow it.

The model is lazy-loaded (BGE-small, ~33MB) on first real embed in the process.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def _resolve_vault_root(vault_root) -> Path:
    """Best-effort vault root: explicit arg > $VAULT_ROOT > module-relative.

    Mirrors the resolution idiom in kbai.storage.section_patcher so the hook
    works whether called from the write-agent process (sets $VAULT_ROOT) or
    in-process with vault_root passed directly.
    """
    if vault_root:
        return Path(vault_root)
    if env := os.environ.get("VAULT_ROOT"):
        return Path(env)
    # kbai/embed/reindex_hooks.py -> repo root is three parents up.
    return Path(__file__).resolve().parent.parent.parent


def _read_summary(note_path: Path) -> str | None:
    """Parse YAML frontmatter from a note file and return its `summary`.

    Returns None when the file has no frontmatter block or no summary field.
    """
    text = note_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    # Split on the frontmatter fences: ["", <yaml>, <body...>].
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    fm = yaml.safe_load(parts[1]) or {}
    if not isinstance(fm, dict):
        return None
    summary = fm.get("summary")
    return summary if (summary and str(summary).strip()) else None


def update_note_embeddings(note_id: str, vault_root=None) -> dict:
    """Embed one freshly-written note into the live sqlite-vec index.

    Returns a status dict; NEVER raises (the create path swallows failures, but
    we also fail soft here so a malformed note can't break the write).
    """
    if not isinstance(note_id, str) or not note_id:
        return {"status": "error", "error": "note_id required"}

    try:
        root = _resolve_vault_root(vault_root)

        from kbai.storage.note_io import find_note_file

        note_path = find_note_file(note_id, root)
        if note_path is None:
            logger.warning("reindex_embed: note file not found note=%s", note_id)
            return {
                "status": "skipped",
                "note_id": note_id,
                "reason": "note_file_not_found",
            }

        summary = _read_summary(note_path)
        if not summary:
            logger.info("reindex_embed: no summary note=%s", note_id)
            return {
                "status": "skipped",
                "note_id": note_id,
                "reason": "no_summary",
            }

        from kbai.embed.indexer import embed_note  # lazy: avoids import cost

        db_path = root / "06-Maps" / "vault-embeddings.db"
        rel = str(note_path.relative_to(root)) if note_path.is_relative_to(root) else ""
        embedded = embed_note(
            note_id,
            summary,
            db_path,
            filepath=rel,
        )
        logger.info("reindex_embed: note=%s embedded=%s", note_id, embedded)
        return {
            "status": "embedded" if embedded else "unchanged",
            "note_id": note_id,
            "embedded": bool(embedded),
        }
    except Exception as exc:  # fail soft — never break the write path
        logger.exception("reindex_embed failed note=%s", note_id)
        return {"status": "error", "note_id": note_id, "error": str(exc)}
