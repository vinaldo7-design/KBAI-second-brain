"""Stage 0 item 8: incremental embedding-reindex hook.

Stub — logs the intent, never triggers a full rebuild. Stage 1 will move
real incremental embedding logic here (per-note re-embed using the existing
hash-based skip in vault_embed.py).

Contract: accepts a single note_id. MUST NOT call vault_embed.main or
otherwise rebuild the whole index.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def update_note_embeddings(note_id: str) -> dict:
    if not isinstance(note_id, str) or not note_id:
        return {"status": "error", "error": "note_id required"}
    logger.info("would_re_embed note=%s", note_id)
    return {
        "status": "stub",
        "note_id": note_id,
        "would_re_embed": True,
        "stage": 0,
        "message": "Real per-note embedding refresh lands in Stage 1.",
    }
