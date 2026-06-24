"""Retrieval quality metrics — pure functions over a ranked list of note_ids."""

from __future__ import annotations


def reciprocal_rank(ranked: list[str], expected) -> float:
    """1 / rank of the first expected note in `ranked` (0 if none present)."""
    es = set(expected)
    for i, nid in enumerate(ranked):
        if nid in es:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(ranked: list[str], expected, k: int = 10) -> float:
    """Fraction of expected notes appearing in the top-k of `ranked`."""
    es = set(expected)
    if not es:
        return 0.0
    return len(es & set(ranked[:k])) / len(es)


def hit_at_k(ranked: list[str], target: str, k: int = 3) -> float:
    """1.0 if `target` is in the top-k of `ranked`, else 0.0."""
    return 1.0 if target in ranked[:k] else 0.0
