"""Stage 0 item 8: incremental graph-edge reindex hook.

Stub — logs the intent, never triggers a full rebuild. Stage 1 will move
real per-note edge reparse logic here.

Contract: accepts a single note_id. MUST NOT call vault_graph.build_graph
or otherwise walk the whole vault.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def update_note_edges(note_id: str) -> dict:
    if not isinstance(note_id, str) or not note_id:
        return {"status": "error", "error": "note_id required"}
    logger.info("would_reparse_edges note=%s", note_id)
    return {
        "status": "stub",
        "note_id": note_id,
        "would_reparse_edges": True,
        "stage": 0,
        "message": "Real per-note edge reparse lands in Stage 1.",
    }
