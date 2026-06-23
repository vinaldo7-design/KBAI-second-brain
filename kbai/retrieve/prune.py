"""Path/result pruning for the retrieval pipeline — pure function, no state.

PathRAG's finding: the limitation of graph-based RAG is the *redundancy* of
retrieved information, not its insufficiency — a long tail of weakly-connected
notes adds noise, dilutes focus, and burns tokens. This trims that tail.

Conservative by design (safe default): a note survives if its PPR score is at
least `min_ratio` x the top score, OR it is a seed (a direct dense/keyword
match — always kept). The result is never pruned below `keep_min` notes, so a
flat or low-scoring ranking is left intact rather than gutted.
"""

from __future__ import annotations


def prune_redundant_paths(
    ranked: list[tuple[str, float]],
    seed_ids,
    *,
    min_ratio: float = 0.05,
    keep_min: int = 10,
) -> list[tuple[str, float]]:
    """Trim the low-reliability tail of a PPR ranking.

    Args:
        ranked:   [(note_id, ppr_score)] sorted by score descending.
        seed_ids: note_ids that are direct seeds — always retained.
        min_ratio: keep notes scoring >= min_ratio * top_score.
        keep_min: never return fewer than this many (when the input has more).

    Returns the surviving [(note_id, score)] in the input's (descending) order.
    """
    if len(ranked) <= keep_min:
        return list(ranked)

    seeds = set(seed_ids)
    top = ranked[0][1] if ranked[0][1] > 0 else 1.0
    threshold = min_ratio * top

    kept = [(nid, s) for nid, s in ranked if s >= threshold or nid in seeds]
    if len(kept) >= keep_min:
        return kept

    # Threshold pruned too hard (flat/low ranking) — fall back to the top keep_min,
    # then union in any seeds that fell outside it, preserving descending order.
    floor = list(ranked[:keep_min])
    floor_ids = {nid for nid, _ in floor}
    extra_seeds = [(nid, s) for nid, s in ranked if nid in seeds and nid not in floor_ids]
    merged = floor + extra_seeds
    merged.sort(key=lambda x: -x[1])
    return merged
