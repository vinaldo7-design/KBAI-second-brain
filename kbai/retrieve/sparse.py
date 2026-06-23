"""Sparse (BM25 / keyword) seed retrieval + hybrid fusion.

Dense embeddings miss literal-keyword matches phrased outside the model's
semantic neighbourhood; BM25 over note summaries catches them. `hybrid_seed`
fuses dense + BM25 seed lists with reciprocal-rank fusion (RRF) and is a drop-in
for `dense_seed`. If the FTS5 index isn't built yet, BM25 returns empty and the
hybrid degrades to dense-only — a safe default, never a regression.
"""

from __future__ import annotations

import re
import sqlite3

_TERM_RE = re.compile(r"\w+", re.UNICODE)


def bm25_seed(query: str, db_path, seed_k: int = 5):
    """Keyword seed via sqlite FTS5 bm25() over note summaries.

    Returns (scores, meta) ordered best-first. Empty — and never raising — when
    the query has no word terms or the `notes_fts` index is absent. The query is
    reduced to bare word terms joined with OR, so FTS5-special punctuation in the
    user's query can't break the MATCH.
    """
    terms = _TERM_RE.findall(query.lower())
    if not terms:
        return {}, {}
    match = " OR ".join(terms)

    db = sqlite3.connect(str(db_path))
    try:
        rows = db.execute(
            "SELECT f.note_id, bm25(notes_fts) AS score, n.title, n.summary, n.filepath "
            "FROM notes_fts f JOIN notes n ON n.id = f.note_id "
            "WHERE notes_fts MATCH ? ORDER BY score LIMIT ?",
            (match, seed_k),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}, {}  # notes_fts not built yet → dense-only fallback upstream
    finally:
        db.close()

    scores: dict[str, float] = {}
    meta: dict[str, dict] = {}
    for nid, score, title, summary, fp in rows:
        # bm25() returns a negative score (more negative = better); flip so higher=better.
        scores[nid] = -float(score)
        meta[nid] = {"title": title, "summary": summary, "filepath": fp}
    return scores, meta


def _rrf(rankings: list[list[str]], rrf_k: int = 60) -> dict[str, float]:
    """Reciprocal rank fusion over best-first id lists → {id: fused_score}.
    rrf_k dampens the contribution of lower ranks (standard default 60)."""
    fused: dict[str, float] = {}
    for ids in rankings:
        for rank, nid in enumerate(ids):
            fused[nid] = fused.get(nid, 0.0) + 1.0 / (rrf_k + rank + 1)
    return fused


def hybrid_seed(query: str, db_path, model, seed_k: int = 5):
    """Dense + BM25 seeds fused by RRF. Drop-in for `dense_seed` — returns
    (seed_scores, seed_meta). Degrades to dense-only when BM25 yields nothing."""
    from kbai.retrieve.dense import dense_seed

    dense_scores, dense_meta = dense_seed(query, db_path, model, seed_k)
    bm25_scores, bm25_meta = bm25_seed(query, db_path, seed_k)
    if not bm25_scores:
        return dense_scores, dense_meta  # dense-only fallback (no FTS index / no match)

    fused = _rrf([list(dense_scores), list(bm25_scores)])
    top = sorted(fused, key=lambda n: -fused[n])[:seed_k]
    seed_scores = {nid: fused[nid] for nid in top}
    seed_meta = {nid: (dense_meta.get(nid) or bm25_meta.get(nid)) for nid in top}
    return seed_scores, seed_meta
