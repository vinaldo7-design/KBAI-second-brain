"""Stage 3 item 3 (Step B): bulk-apply link suggestions to vault notes.

Wraps kbai.storage.section_patcher.patch_section over a list of
suggestions. Each suggestion targets the source note's typed-link
section (### Builds on, etc.) and inserts `- [[target_id]]`.

Status taxonomy for each row:
  patched          — file changed, journal row written
  already_present  — link already there, file unchanged, no journal row
  no_section       — heading not found in source file
  missing_file     — source note resolves to no file

The aggregate receipt is always status="applied" — even if every row
landed in one of the non-success buckets — because the *bulk operation*
itself completed. Callers inspect `results` and `counts` for detail.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from kbai.contracts import WriteReceipt
from kbai.embed.reindex_hooks import update_note_embeddings
from kbai.graph.reindex_hooks import update_note_edges
from kbai.storage.note_io import find_note_file
from kbai.storage.section_patcher import patch_section
from kbai.storage.write_journal import record_mutation


_TOOL = "write_apply_link_suggestions"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel_or_abs(p: Path, vault_root: Path) -> str:
    try:
        return str(p.relative_to(vault_root))
    except ValueError:
        return str(p)


def _normalise(s: dict) -> tuple[str, str, str, str] | None:
    """Extract (source_id, target_id, edge_type, section) from a suggestion
    dict. Accepts both new-style keys (source_id/target_id) and legacy
    keys (source/target/suggested_type) so existing analytics output works.
    Returns None on missing required fields."""
    if not isinstance(s, dict):
        return None
    source_id = s.get("source_id") or s.get("source")
    target_id = s.get("target_id") or s.get("target")
    edge_type = s.get("edge_type") or s.get("suggested_type")
    section = s.get("section") or ""
    if not (isinstance(source_id, str) and source_id):
        return None
    if not (isinstance(target_id, str) and target_id):
        return None
    if not (isinstance(edge_type, str) and edge_type):
        return None
    return source_id, target_id, edge_type, section


def apply_link_suggestions(
    vault_root: Path,
    suggestions: list[dict],
    dryrun: bool = False,
) -> WriteReceipt:
    """Apply N link suggestions. Always returns a WriteReceipt with
    aggregate counts and a per-suggestion `results` list."""
    vault_root = Path(vault_root)

    if not isinstance(suggestions, list):
        return WriteReceipt(
            status="error",
            tool=_TOOL,
            applied=False,
            message="suggestions must be a list",
        )

    counts = {"patched": 0, "already_present": 0, "no_section": 0, "missing_file": 0, "invalid": 0}
    results: list[dict] = []

    for idx, raw in enumerate(suggestions):
        norm = _normalise(raw)
        if norm is None:
            counts["invalid"] += 1
            results.append(
                {"index": idx, "status": "invalid", "reason": "missing required fields"}
            )
            continue
        source_id, target_id, edge_type, section = norm

        source_file = find_note_file(source_id, vault_root)
        if source_file is None:
            counts["missing_file"] += 1
            results.append(
                {
                    "index": idx,
                    "source_id": source_id,
                    "target_id": target_id,
                    "edge_type": edge_type,
                    "status": "missing_file",
                }
            )
            continue

        try:
            original = source_file.read_text(encoding="utf-8")
        except OSError as e:
            counts["missing_file"] += 1
            results.append(
                {
                    "index": idx,
                    "source_id": source_id,
                    "status": "missing_file",
                    "reason": f"read failed: {e}",
                }
            )
            continue

        hash_before = hashlib.sha256(source_file.read_bytes()).hexdigest()
        new_text, status = patch_section(original, edge_type, target_id)
        rel_file = _rel_or_abs(source_file, vault_root)

        if status == "already_present":
            counts["already_present"] += 1
            results.append(
                {
                    "index": idx,
                    "source_id": source_id,
                    "target_id": target_id,
                    "edge_type": edge_type,
                    "status": "already_present",
                    "file": rel_file,
                }
            )
            continue

        if status == "no_section":
            counts["no_section"] += 1
            results.append(
                {
                    "index": idx,
                    "source_id": source_id,
                    "target_id": target_id,
                    "edge_type": edge_type,
                    "status": "no_section",
                    "file": rel_file,
                }
            )
            continue

        # status == "patched"
        if dryrun:
            counts["patched"] += 1
            results.append(
                {
                    "index": idx,
                    "source_id": source_id,
                    "target_id": target_id,
                    "edge_type": edge_type,
                    "status": "patched",
                    "dryrun": True,
                    "file": rel_file,
                    "hash_before": hash_before,
                }
            )
            continue

        try:
            source_file.write_text(new_text, encoding="utf-8")
        except OSError as e:
            results.append(
                {
                    "index": idx,
                    "source_id": source_id,
                    "status": "error",
                    "reason": f"write failed: {e}",
                }
            )
            continue

        hash_after = hashlib.sha256(source_file.read_bytes()).hexdigest()
        update_note_embeddings(source_id)
        update_note_edges(source_id)

        journal_id = record_mutation(
            vault_root=vault_root,
            tool=_TOOL,
            note_id=source_id,
            file=rel_file,
            hash_before=hash_before,
            hash_after=hash_after,
            status="patched",
            dryrun=False,
            payload_json=json.dumps(
                {
                    "target_id": target_id,
                    "edge_type": edge_type,
                    "section": section,
                }
            ),
        )

        counts["patched"] += 1
        results.append(
            {
                "index": idx,
                "source_id": source_id,
                "target_id": target_id,
                "edge_type": edge_type,
                "status": "patched",
                "file": rel_file,
                "hash_before": hash_before,
                "hash_after": hash_after,
                "journal_id": journal_id,
            }
        )

    now = _now_iso()
    applied_any = any(
        r.get("status") == "patched" and not r.get("dryrun") for r in results
    )
    return WriteReceipt(
        status="applied",
        tool=_TOOL,
        applied=applied_any,
        dryrun=dryrun,
        ts=now,
        applied_at=now if not dryrun else None,
        counts=counts,
        results=results,
        total=len(suggestions),
    )
