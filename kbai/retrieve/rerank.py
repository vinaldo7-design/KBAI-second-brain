"""Cross-encoder reranking — reorder first-stage candidates by query<->summary
relevance. The first stage (dense+BM25 → PPR) optimises *recall* (find the right
cluster); the cross-encoder fixes *order* (a generic map/MOC note PPR over-ranks
scores low against a specific query and gets demoted). Local, free; model loads
lazily and only when reranking is actually used.
"""

from __future__ import annotations

_model = None
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def get_cross_encoder(model_name: str = DEFAULT_MODEL):
    """Lazily load + cache the cross-encoder (downloads ~80MB on first use)."""
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder

        _model = CrossEncoder(model_name)
    return _model


def cross_encoder_scorer(model=None):
    """Return a scorer(query, texts) -> list[float] backed by a cross-encoder.

    Loads the model lazily on first call. If the model can't be loaded (e.g. no
    network on first download), returns None so callers run rerank-free."""
    try:
        m = model or get_cross_encoder()
    except Exception:
        return None

    def score(query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        return [float(s) for s in m.predict([(query, t) for t in texts])]

    return score


def rerank_ranked(query, ranked, summary_of, scorer):
    """Reorder a [(note_id, first_stage_score)] list by cross-encoder relevance.

    Args:
        query:      the user query.
        ranked:     [(note_id, score)] from the first stage.
        summary_of: callable(note_id) -> summary text (or None).
        scorer:     callable(query, list[str]) -> list[float], higher = better.

    Original (note_id, score) tuples are preserved — only their order changes.
    Never raises on empty input.
    """
    if not ranked:
        return list(ranked)
    texts = [summary_of(nid) or "" for nid, _ in ranked]
    scores = scorer(query, texts)
    order = sorted(range(len(ranked)), key=lambda i: -scores[i])
    return [ranked[i] for i in order]
