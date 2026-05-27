"""Path attribution helpers — pure functions, no server state."""

from __future__ import annotations


def path_exclude_from_profile(profile) -> set[str]:
    """Derive path-exclusion edge types from a CognitiveProfile.

    Always drops structural noise (referenced-in, untyped), then gates
    contradicts and mentioned based on the profile's policies.
    """
    exclude = {"referenced-in", "untyped"}
    if profile.contradiction_policy == "suppress":
        exclude.add("contradicts")
    if profile.mention_policy == "ignore":
        exclude.add("mentioned")
    return exclude


def path_attribute(
    graph,
    seed_ids: list[str],
    ppr_targets: list[str],
    path_exclude_types: set[str],
    include_mentioned: bool = False,
) -> dict[str, str | None]:
    """Return {note_id: reasoning_path} for each target."""
    return graph.path_attributions(
        seed_ids, ppr_targets,
        exclude_types=path_exclude_types,
        include_mentioned=include_mentioned,
    )
