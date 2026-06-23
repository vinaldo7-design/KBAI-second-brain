"""Stage 3 item 1: create a new vault note.

Validated, idempotent-safe (refuses to overwrite), journal-aware. The MCP
tool wrapper in writeagentmcp/server.py is ≤5 lines and delegates here.

Allowed folders match the vault's canonical top-level layout.
Note id must be kebab-case to match link/wikilink conventions.

Side effects:
  - Writes one file (unless dryrun).
  - Calls reindex hooks (still stubs — Stage 1).
  - Appends one row to the write journal (unless dryrun).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

from kbai.contracts import WriteReceipt
from kbai.embed.reindex_hooks import update_note_embeddings
from kbai.graph.reindex_hooks import update_note_edges
from kbai.schema import CANONICAL_FIELD_ORDER, validate_frontmatter
from kbai.storage.write_journal import record_mutation
from kbai.templates import render_body


logger = logging.getLogger(__name__)

_TOOL = "write_create_note"

_ALLOWED_FOLDERS: frozenset[str] = frozenset(
    {
        "00-Captures",
        "01-Ideas",
        "02-Learning",
        "03-Projects",
        "04-Substack",
        "05-Personal",
        "06-Maps",
    }
)

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _error_receipt(message: str, note_id: str | None = None) -> WriteReceipt:
    return WriteReceipt(
        status="error",
        tool=_TOOL,
        note_id=note_id,
        applied=False,
        message=message,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ordered_frontmatter(
    note_id: str,
    user_fields: dict,
    now_iso: str,
) -> dict:
    """Merge user-supplied frontmatter with computed defaults, preserving the
    canonical field order from kbai.schema.CANONICAL_FIELD_ORDER."""
    merged: dict = {}
    defaults = {
        "id": note_id,
        "created": now_iso,
        "updated": now_iso,
    }
    user_fields = dict(user_fields or {})
    # Step 1: canonical-order fields (defaults overridden by user values if present).
    for key in CANONICAL_FIELD_ORDER:
        if key in user_fields:
            merged[key] = user_fields.pop(key)
        elif key in defaults:
            merged[key] = defaults[key]
    # Step 2: any remaining user fields, preserving their order.
    for k, v in user_fields.items():
        merged[k] = v
    return merged


def create_note(
    vault_root: Path,
    folder: str,
    note_id: str,
    frontmatter: dict,
    body: str,
    dryrun: bool = False,
) -> WriteReceipt:
    """Create a new note. Returns a WriteReceipt; never raises on
    validation/IO problems — failures are reported in the receipt."""
    vault_root = Path(vault_root)

    # --- validation -------------------------------------------------------
    if not isinstance(note_id, str) or not note_id:
        return _error_receipt("note_id must be a non-empty string", note_id)
    if not _KEBAB_RE.match(note_id):
        return _error_receipt(
            f"note_id '{note_id}' is not kebab-case "
            "(lowercase letters, digits, hyphens; no leading/trailing hyphen)",
            note_id,
        )
    if folder not in _ALLOWED_FOLDERS:
        return _error_receipt(
            f"folder '{folder}' is not one of {sorted(_ALLOWED_FOLDERS)}",
            note_id,
        )
    if not isinstance(frontmatter, dict):
        return _error_receipt("frontmatter must be a dict", note_id)
    if not isinstance(body, str):
        return _error_receipt("body must be a string", note_id)

    folder_path = vault_root / folder
    target = folder_path / f"{note_id}.md"
    rel_file = f"{folder}/{note_id}.md"

    if target.exists():
        return WriteReceipt(
            status="error",
            tool=_TOOL,
            note_id=note_id,
            applied=False,
            file=rel_file,
            message=f"refuses to overwrite existing note at {rel_file}",
        )

    # --- render -----------------------------------------------------------
    now_iso = _now_iso()
    fm = _ordered_frontmatter(note_id, frontmatter, now_iso)

    # --- schema validation (Phase 4: hard gate before any write_text) -----
    schema_error = validate_frontmatter(fm)
    if schema_error is not None:
        return _error_receipt(schema_error, note_id)

    try:
        yaml_block = yaml.safe_dump(
            fm, sort_keys=False, allow_unicode=True
        )
    except yaml.YAMLError as e:
        return _error_receipt(f"frontmatter is not YAML-serialisable: {e}", note_id)

    # Phase 6a: empty body → render the canonical skeleton for this type.
    # Non-empty body flows through verbatim (backward-compatible).
    if body == "":
        body = render_body(
            fm["type"], title=str(fm.get("title", "")), summary=str(fm.get("summary", "")),
        )

    content = f"---\n{yaml_block}---\n\n{body}"

    # --- dryrun ----------------------------------------------------------
    if dryrun:
        return WriteReceipt(
            status="dry_run",
            tool=_TOOL,
            note_id=note_id,
            applied=False,
            dryrun=True,
            file=rel_file,
            hash_before=None,
            hash_after=None,
            ts=now_iso,
            message=f"dryrun — would create {rel_file} ({len(content)} chars)",
        )

    # --- write ------------------------------------------------------------
    folder_path.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(content, encoding="utf-8")
    except OSError as e:
        return _error_receipt(f"write failed: {e}", note_id)

    hash_after = hashlib.sha256(target.read_bytes()).hexdigest()

    # Reindex hooks. update_note_embeddings is now REAL (loads BGE on first
    # call in this process, opens + writes the sqlite-vec DB), so its failure
    # must never break the create: wrap it and swallow. The write already
    # succeeded above; the receipt stays status="applied" regardless.
    # update_note_edges is still a no-op stub, so it's left unwrapped.
    # NOTE / latent issue: link_applier and research_appender call their reindex
    # hooks unwrapped too — once those hooks do real I/O they need the same
    # try/except guard. Flagged for a later pass; not touched here.
    try:
        update_note_embeddings(note_id, vault_root)
    except Exception:  # noqa: BLE001 — hook failure must not fail the write
        logger.exception("update_note_embeddings hook failed note=%s", note_id)
    update_note_edges(note_id)

    journal_id = record_mutation(
        vault_root=vault_root,
        tool=_TOOL,
        note_id=note_id,
        file=rel_file,
        hash_before=None,
        hash_after=hash_after,
        status="applied",
        dryrun=False,
        payload_json=json.dumps(
            {"folder": folder, "body_chars": len(body), "fm_keys": list(fm.keys())}
        ),
    )

    return WriteReceipt(
        status="applied",
        tool=_TOOL,
        note_id=note_id,
        applied=True,
        dryrun=False,
        file=rel_file,
        hash_before=None,
        hash_after=hash_after,
        ts=now_iso,
        applied_at=now_iso,
        journal_id=journal_id,
    )
