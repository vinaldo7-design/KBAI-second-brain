"""Apply a CognitiveProfile to a base PPR config.

Returns a dict of effective parameters that the retrieval module can plug
straight into `VaultGraph.ppr_expand`.

This module is the integration point for Stage 5.5.3 (refactoring
`_assemble_context_impl` to take `profile_id`). Until that lands, the applier
is exercised only by tests + the read-side `cognition_get_profile` MCP tool.

Hints (`path_length_hint`, `abstraction_hint`) are passed through but not
yet consumed — current PPR / path-attribution code does not parameterise
them. Stage 5.5.3 wires them in.
"""

from __future__ import annotations

from kbai.contracts import CognitiveProfile


def apply_profile(
    profile: CognitiveProfile,
    base_taxonomy_weights: dict[str, float],
    base_exclude_types: set[str] | None = None,
) -> dict:
    """Compute effective PPR config from a base config + profile.

    Args:
        profile: a CognitiveProfile loaded from the registry
        base_taxonomy_weights: edge_type → weight (from vault_taxonomy.yaml)
        base_exclude_types: edges always excluded regardless of profile (e.g.
            mode-level exclusions); profile policy is layered on top

    Returns:
        dict with:
        - effective_weights: edge_type → weight after profile multipliers
        - effective_exclude_types: set of edge types to gate out of the walk
        - path_length_hint, abstraction_hint: forwarded for downstream use
        - profile_id: source profile
    """
    base_exclude = set(base_exclude_types or set())

    # Edge weight overrides multiply the base taxonomy weights.
    effective_weights = dict(base_taxonomy_weights)
    for et, mult in profile.edge_weight_overrides.items():
        effective_weights[et] = effective_weights.get(et, 1.0) * float(mult)

    # Contradiction policy.
    effective_exclude = set(base_exclude)
    if profile.contradiction_policy == "suppress":
        effective_exclude.add("contradicts")
    elif profile.contradiction_policy == "seek":
        effective_exclude.discard("contradicts")
    # "allow" → leave whatever the base says

    # Mention policy.
    if profile.mention_policy == "ignore":
        effective_exclude.add("mentioned")
    # "exhaustive" → leave it; caller is expected to supply a graph that has
    # mentioned edges loaded (i.e. include_mentioned=True at VaultGraph load).

    return {
        "profile_id": profile.profile_id,
        "effective_weights": effective_weights,
        "effective_exclude_types": effective_exclude,
        "path_length_hint": profile.path_length_preference,
        "abstraction_hint": profile.abstraction_preference,
        "restart_bias_tags": dict(profile.restart_bias_tags),
        "confidence_threshold": float(profile.confidence_threshold),
    }
