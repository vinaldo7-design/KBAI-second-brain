"""Council Mode — multi-profile retrieval with overlap analysis.

Stage 5.6. Three-profile council (explorer, operator, skeptic) is the default
preset. Synthesis (the fourth role) is Claude reading the CouncilEvidence
bundle via the /council slash command — no separate synthesis agent.

The functions in this module are pure / dependency-injected so they can be
unit-tested without sentence-transformers or a real graph. The MCP tool
in minivinnymcp/server.py supplies the real `retrieve_fn`.
"""

from __future__ import annotations

from typing import Callable

from kbai.contracts import (
    CognitiveProfile,
    ContextNote,
    CouncilEvidence,
    CouncilProfileResult,
)
from kbai.cognitive_routing import load_profile

DEFAULT_COUNCIL_PROFILES: list[str] = ["explorer", "operator", "skeptic"]


def profile_focus_summary(profile: CognitiveProfile) -> str:
    """One-line machine summary of what this lens prioritises. Read by the
    synthesizer prompt so the LLM doesn't have to introspect the profile."""
    parts: list[str] = []
    boosts = sorted(profile.edge_weight_overrides.items(), key=lambda kv: -kv[1])
    top_boosts = [et for et, mult in boosts if mult > 1.0][:2]
    if top_boosts:
        parts.append("boosts " + ", ".join(top_boosts))
    if profile.contradiction_policy == "seek":
        parts.append("seeks contradictions")
    elif profile.contradiction_policy == "allow":
        parts.append("allows contradictions")
    if profile.path_length_preference != "balanced":
        parts.append(f"{profile.path_length_preference} paths")
    if profile.abstraction_preference != "balanced":
        parts.append(f"{profile.abstraction_preference} bias")
    return "; ".join(parts) if parts else "default behaviour"


def build_council_evidence(
    query: str,
    per_profile: dict[str, list[ContextNote]],
    profile_summaries: dict[str, tuple[str, str]] | None = None,
    top_k: int = 10,
) -> CouncilEvidence:
    """Pure function: given per-profile top-k note lists, compute overlap
    analysis and assemble a CouncilEvidence.

    Args:
        query: original user query
        per_profile: profile_id → list of ContextNote (already truncated to top_k)
        profile_summaries: profile_id → (display_name, focus_summary). Optional;
            if missing, sensible defaults are used.
        top_k: forwarded into the result for downstream display

    Returns:
        CouncilEvidence with consensus / unanimous / unique_to populated.
    """
    profile_ids = list(per_profile.keys())
    summaries = profile_summaries or {}

    # Tally how many profiles surfaced each note id.
    surface_count: dict[str, int] = {}
    surface_in: dict[str, set[str]] = {}
    for pid, notes in per_profile.items():
        for n in notes:
            surface_count[n.note_id] = surface_count.get(n.note_id, 0) + 1
            surface_in.setdefault(n.note_id, set()).add(pid)

    n_profiles = len(profile_ids)
    consensus = sorted(nid for nid, c in surface_count.items() if c >= 2)
    unanimous = sorted(nid for nid, c in surface_count.items() if c == n_profiles and n_profiles > 1)
    unique_to: dict[str, list[str]] = {pid: [] for pid in profile_ids}
    for nid, profs in surface_in.items():
        if len(profs) == 1:
            (only,) = profs
            unique_to[only].append(nid)
    for pid in unique_to:
        unique_to[pid].sort()

    per_profile_results: list[CouncilProfileResult] = []
    for pid in profile_ids:
        display_name, focus = summaries.get(pid, (pid.title(), "default behaviour"))
        per_profile_results.append(CouncilProfileResult(
            profile_id=pid,
            display_name=display_name,
            focus_summary=focus,
            notes=per_profile[pid],
        ))

    return CouncilEvidence(
        query=query,
        profiles=profile_ids,
        per_profile=per_profile_results,
        consensus=consensus,
        unanimous=unanimous,
        unique_to=unique_to,
        top_k=top_k,
        coverage_count=len(surface_count),
    )


def run_council(
    query: str,
    profile_ids: list[str] | None,
    top_k: int,
    retrieve_fn: Callable[[str, str, int], list[ContextNote]],
) -> CouncilEvidence:
    """Run the council. `retrieve_fn(query, profile_id, top_k)` returns a
    list of ContextNote; this layer only assembles the evidence.

    Profile loading happens here so the focus summaries can be computed
    once per profile, not by the caller.
    """
    profile_ids = profile_ids or list(DEFAULT_COUNCIL_PROFILES)

    summaries: dict[str, tuple[str, str]] = {}
    per_profile: dict[str, list[ContextNote]] = {}
    for pid in profile_ids:
        try:
            profile = load_profile(pid)
        except FileNotFoundError:
            # Skip unknown profiles; we still build a valid evidence with whatever loads.
            continue
        summaries[pid] = (profile.display_name, profile_focus_summary(profile))
        per_profile[pid] = retrieve_fn(query, pid, top_k)

    return build_council_evidence(
        query=query,
        per_profile=per_profile,
        profile_summaries=summaries,
        top_k=top_k,
    )
