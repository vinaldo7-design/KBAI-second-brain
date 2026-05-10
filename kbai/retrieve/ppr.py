"""PPR expansion — pure function, no server state."""

from __future__ import annotations


def ppr_rank(
    graph,
    seed_scores: dict[str, float],
    exclude_types: set[str],
    weight_overrides: dict[str, float],
    cap: int = 50,
) -> list[tuple[str, float]]:
    """Run PPR seeded by dense scores and return sorted [(note_id, score)].

    Results are capped at `cap` and filtered to nodes that exist in the graph.
    """
    ppr_scores = graph.ppr_expand(
        seed_scores,
        exclude_types=exclude_types,
        weight_overrides=weight_overrides,
    )
    return sorted(
        ((nid, score) for nid, score in ppr_scores.items() if graph.exists(nid)),
        key=lambda x: -x[1],
    )[:cap]
