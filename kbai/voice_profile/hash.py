"""Stage 0 item 9: stable hash of a set of voice-exemplar notes.

Stable for identical inputs, sensitive to any content change. Used by
the voice-profile cache so `/voice vinay` recompiles only when an exemplar's
content actually changes.
"""

from __future__ import annotations

import hashlib
from typing import Iterable


def compute_voice_exemplar_hash(notes: Iterable[tuple[str, str]]) -> str:
    """Compute a deterministic sha256 over (note_id, body) pairs.

    Args:
        notes: iterable of (note_id, body_text). Order does not matter.

    Returns:
        64-char hex digest. Same content → same hash; any change → different hash.
    """
    items = sorted((str(nid), body or "") for nid, body in notes)
    h = hashlib.sha256()
    for note_id, body in items:
        h.update(note_id.encode("utf-8"))
        h.update(b"\x00")
        h.update(hashlib.sha256(body.encode("utf-8")).digest())
        h.update(b"\x00")
    return h.hexdigest()
