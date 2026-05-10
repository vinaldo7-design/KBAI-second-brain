"""Dense (vector) seed retrieval — pure function, no server state."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec


def dense_seed(
    query: str,
    db_path: Path,
    model,
    seed_k: int = 5,
) -> tuple[dict[str, float], dict[str, dict]]:
    """Run ANN search and return (seed_scores, seed_meta) keyed by note_id.

    seed_scores[nid] = cosine similarity in [0, 1]
    seed_meta[nid]   = {title, summary, filepath}
    """
    from vault_search import serialize_embedding, QUERY_PREFIX

    qvec = model.encode(QUERY_PREFIX + query, normalize_embeddings=True)

    db = sqlite3.connect(db_path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    rows = db.execute(
        """
        SELECT v.note_id, v.distance, n.title, n.summary, n.filepath
        FROM note_vectors v
        JOIN notes n ON n.id = v.note_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (serialize_embedding(qvec), seed_k),
    ).fetchall()
    db.close()

    seed_scores: dict[str, float] = {}
    seed_meta: dict[str, dict] = {}
    for nid, dist, title, summary, fp in rows:
        sim = max(0.0, 1.0 - float(dist))
        seed_scores[nid] = sim
        seed_meta[nid] = {"title": title, "summary": summary, "filepath": fp}

    return seed_scores, seed_meta
