"""What must happen after a note's file is written: reindex it and journal it.

The file is already on disk, so nothing here may fail the write or stop a batch.
Problems are returned instead, for the receipt to report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kbai.embed.reindex_hooks import update_note_embeddings
from kbai.graph.reindex_hooks import update_note_edges
from kbai.storage.write_journal import record_mutation


@dataclass
class PostWrite:
    index_status: dict[str, str]
    journal_id: int | None = None
    journal_error: str | None = None
    problems: list[str] = field(default_factory=list)


def finish_write(vault_root: Path, note_id: str, **journal_fields) -> PostWrite:
    """Reindex note_id and record the mutation. Never raises on either step."""
    results = {
        "embeddings": update_note_embeddings(note_id, vault_root),
        "graph": update_note_edges(note_id, vault_root),
    }
    outcome = PostWrite(index_status={name: r["status"] for name, r in results.items()})
    for name, result in results.items():
        if result["status"] == "error":
            outcome.problems.append(f"not indexed ({name}): {result.get('error')}")

    try:
        outcome.journal_id = record_mutation(
            vault_root=vault_root, note_id=note_id, dryrun=False, **journal_fields
        )
    except Exception as exc:  # noqa: BLE001 — a locked journal must not undo a saved note
        outcome.journal_error = str(exc)
        outcome.problems.append(f"journal write failed: {exc}")
    return outcome
