"""Unified retrieval assembler (Stage 1.4 + 5.5.3).

Single code path for both the legacy mode= API and the new profile_id= API.

Legacy path (mode given, profile=None):
  - mode is mapped to a profile for graph-selection + exclude logic only.
  - weight_overrides are FORCED to {} to preserve byte-identical top-N scores.
  - top_k=50, char_budget consumed, attr_top_n=15.

Profile path (profile given):
  - Profile drives exclude_types AND weight_overrides (full profile semantics).
  - top_k set by caller (council uses 10), char_budget=0 skips content loading.
  - attr_top_n=None attributes all returned results.

Mode → profile mapping (for one deprecation cycle; mode= will be removed in Stage 5):
  standard   → default   (contradicts+mentioned excluded, no weight overrides)
  sparring   → skeptic   (mentioned excluded, contradicts seek — overrides suppressed on legacy path)
  exhaustive → exhaustive (all edges admitted — caller must supply exhaustive graph)
"""

from __future__ import annotations

from pathlib import Path

from kbai.cognitive_routing import apply_profile, load_profile
from kbai.contracts import CognitiveProfile
from kbai.retrieve.dense import dense_seed
from kbai.retrieve.path import path_attribute, path_exclude_from_profile
from kbai.retrieve.ppr import ppr_rank
from kbai.retrieve.prune import prune_redundant_paths

_MODE_TO_PROFILE: dict[str, str] = {
    "standard": "default",
    "sparring": "skeptic",
    "exhaustive": "exhaustive",
}


def assemble_context(
    *,
    query: str,
    db_path: Path,
    vault_root: Path,
    graph,
    model,
    mode: str | None = None,
    profile: CognitiveProfile | None = None,
    seed_k: int = 5,
    char_budget: int = 12000,
    top_k: int = 50,
    attr_top_n: int | None = 15,
) -> dict:
    """Full hybrid retrieval: dense seed → PPR → char-budget content → path attribution.

    Pass either `profile` (new path) or `mode` (legacy path).  When both are
    supplied, `profile` takes precedence.

    char_budget=0 skips content loading entirely (council / compact callers).
    attr_top_n=None attributes every returned result (profile path default).
    """
    from kbai.storage.note_io import find_note_file

    # ── Resolve profile ──────────────────────────────────────────────────────
    _profile_explicit = profile is not None
    if profile is None:
        resolved_id = _MODE_TO_PROFILE.get(mode or "standard", "default")
        profile = load_profile(resolved_id)

    base_weights = dict(graph.taxonomy_weights)
    effective = apply_profile(profile, base_weights, base_exclude_types=set())
    exclude_types = effective["effective_exclude_types"]

    # Legacy mode path: suppress weight overrides to preserve exact PPR scores.
    weight_overrides = profile.edge_weight_overrides if _profile_explicit else {}

    # Profile.mention_policy = "exhaustive" walks the mentioned-included view;
    # any other policy walks the default view (mentioned excluded).
    include_mentioned = profile.mention_policy == "exhaustive"

    # ── Dense seed ───────────────────────────────────────────────────────────
    seed_scores, seed_meta = dense_seed(query, db_path, model, seed_k)

    # ── PPR ──────────────────────────────────────────────────────────────────
    ranked = ppr_rank(
        graph, seed_scores, exclude_types, weight_overrides,
        cap=top_k, include_mentioned=include_mentioned,
    )

    # ── Prune the redundant tail (PathRAG: redundancy, not insufficiency) ─────
    # Conservative: drops only notes below 5% of the top PPR score, always keeps
    # seeds, never below keep_min. With top_k<=10 (council/profile path) this is
    # a no-op; it only trims the long legacy-mode tail (top_k=50).
    ranked = prune_redundant_paths(ranked, list(seed_meta.keys()))

    # ── Build result list ────────────────────────────────────────────────────
    results: list[dict] = []
    chars_used = 0
    for i, (nid, ppr) in enumerate(ranked):
        node = graph.node(nid) or {}
        if nid in seed_meta:
            title = seed_meta[nid]["title"]
            summary = seed_meta[nid]["summary"]
            source = "seed"
        else:
            title = node.get("title")
            summary = node.get("summary")
            source = "ppr"

        content = None
        if char_budget > 0:
            note_file = find_note_file(nid, vault_root, node)
            if note_file and chars_used < char_budget:
                raw = note_file.read_text(encoding="utf-8")
                remaining = char_budget - chars_used
                if len(raw) <= remaining:
                    content = raw
                    chars_used += len(raw)
                elif i < 3:
                    content = raw[:remaining]
                    chars_used += remaining

        results.append({
            "note_id": nid,
            "title": title,
            "summary": summary,
            "content": content,
            "composite_score": round(ppr, 4),
            "source": source,
            "via_edge": None,
            "parent": None,
        })

    # ── Path attribution ─────────────────────────────────────────────────────
    seed_ids = list(seed_meta.keys())
    attr_slice = results[:attr_top_n] if attr_top_n is not None else results
    ppr_targets = [r["note_id"] for r in attr_slice if r["source"] == "ppr"]
    path_exclude = path_exclude_from_profile(profile)
    attributions = path_attribute(
        graph, seed_ids, ppr_targets, path_exclude,
        include_mentioned=include_mentioned,
    )
    for r in results:
        r["reasoning_path"] = (
            attributions.get(r["note_id"]) if r["source"] == "ppr" else None
        )

    # ── Instrumentation ──────────────────────────────────────────────────────
    mode_label = (
        f"profile:{profile.profile_id}" if _profile_explicit else (mode or "standard")
    )
    try:
        from kbai.instrumentation import record_note_hits
        record_note_hits(db_path, query=query, results=results, mode=mode_label)
    except Exception:
        pass  # never block retrieval on instrumentation

    # ── Return ───────────────────────────────────────────────────────────────
    out: dict = {
        "query": query,
        "notes": results,
        "chars_used": chars_used,
        "char_budget": char_budget,
    }
    if _profile_explicit:
        out["profile_id"] = profile.profile_id
    return out
