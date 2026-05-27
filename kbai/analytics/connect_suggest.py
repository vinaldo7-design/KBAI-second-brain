"""Connect-suggest analytics — pure read functions over the vault graph.

Five categories of suggested links:
  1. Orphan rescue          — zero-typed-edge notes, 3 nearest by shared tags
  2. Missing bidirectional  — A builds-on B but B has no builds-toward A
  3. Tag-cluster gaps       — share 3+ tags, no direct edge → analogous-to candidate
  4. Force-fit re-typing    — annotation >60 chars, edge type may be wrong
  5. Low-centrality high-substance — evergreen notes with PageRank below median

This module is read-only. Mutation is the Write Agent's job (Stage 3 →
write_apply_link_suggestions).

History: Stage 1 physically moved these implementations from
vault_connect_suggest.py (the CLI script at vault root) into kbai/analytics/.
The CLI is now a thin caller of this module.
"""

from __future__ import annotations

import statistics

from vault_graph_loader import VaultGraph

# --- helpers --------------------------------------------------------------


def shared_tags(a: dict, b: dict) -> int:
    ta = set(a.get("topics", [])) | set(a.get("lenses", []))
    tb = set(b.get("topics", [])) | set(b.get("lenses", []))
    return len(ta & tb)


def tag_set(node: dict) -> set:
    return set(node.get("topics", [])) | set(node.get("lenses", []))


def has_edge_between(g: VaultGraph, a: str, b: str) -> bool:
    v = g.view(collapse=True, include_mentioned=False)
    return v.has_edge(a, b) or v.has_edge(b, a)


def typed_degree(g: VaultGraph, node_id: str) -> int:
    v = g.view(collapse=True, include_mentioned=False)
    count = 0
    for _, _, data in v.out_edges(node_id, data=True):
        if data.get("type") not in (None, "untyped", "mentioned"):
            count += 1
    for _, _, data in v.in_edges(node_id, data=True):
        if data.get("type") not in (None, "untyped", "mentioned"):
            count += 1
    return count


# --- Category 1 — Orphan rescue ------------------------------------------


def orphan_rescue(g: VaultGraph) -> list[dict]:
    """For each note with zero typed edges, suggest 3 nearest by shared tags."""
    real_nodes = [
        (nid, data) for nid, data in g.G.nodes(data=True)
        if not data.get("_broken") and data.get("type") not in ("map",)
    ]
    orphans = [(nid, data) for nid, data in real_nodes if typed_degree(g, nid) == 0]
    candidates = real_nodes

    results = []
    for oid, odata in orphans:
        scored = []
        for cid, cdata in candidates:
            if cid == oid:
                continue
            score = shared_tags(odata, cdata)
            if score > 0:
                scored.append((score, cid, cdata))
        scored.sort(key=lambda x: -x[0])
        for score, cid, cdata in scored[:3]:
            results.append({
                "source": oid,
                "target": cid,
                "suggested_type": "analogous-to",
                "confidence": score,
                "reason": f"{score} shared tag(s): {sorted(tag_set(odata) & tag_set(cdata))}",
            })
    return results


# --- Category 2 — Missing bidirectional ----------------------------------


def missing_bidir(g: VaultGraph) -> list[dict]:
    """A builds-on B implies B should have a builds-toward A — and vice versa.

    Iterates native edges (g.G, no collapse). For each `A builds-on B`, looks for
    native `B builds-toward A`; for each `A builds-toward B`, looks for native
    `B builds-on A`. Operating on the collapsed view would conflate the two
    narrations and produce false positives (the pre-2b bug).
    """
    _REVERSE = {"builds-on": "builds-toward", "builds-toward": "builds-on"}
    results = []
    seen = set()
    for source, target, data in g.G.edges(data=True):
        etype = data.get("type")
        expected_reverse_type = _REVERSE.get(etype)
        if expected_reverse_type is None:
            continue
        expected_source, expected_target = target, source

        key = (expected_source, expected_target, expected_reverse_type)
        if key in seen:
            continue

        reverse_exists = False
        for _, tgt, d in g.G.out_edges(expected_source, data=True):
            if tgt == expected_target and d.get("type") == expected_reverse_type:
                reverse_exists = True
                break

        if (
            not reverse_exists
            and g.G.nodes.get(expected_source)
            and not g.G.nodes[expected_source].get("_broken")
        ):
            seen.add(key)
            results.append({
                "source": expected_source,
                "target": expected_target,
                "suggested_type": expected_reverse_type,
                "confidence": "structural",
                "reason": f"{source} --[{etype}]--> {target} exists; reverse {expected_reverse_type} is missing",
            })
    results.sort(key=lambda r: (r["suggested_type"], r["source"]))
    return results


# --- Category 3 — Tag-cluster gaps ---------------------------------------


def tag_cluster_gaps(g: VaultGraph, min_shared: int = 3) -> list[dict]:
    """Pairs sharing min_shared+ tags with no direct edge — analogous-to candidates."""
    real_nodes = [
        (nid, data) for nid, data in g.G.nodes(data=True)
        if not data.get("_broken")
        and data.get("type") not in ("map",)
        and (data.get("topics") or data.get("lenses"))
    ]
    results = []
    seen = set()
    for i, (aid, adata) in enumerate(real_nodes):
        for bid, bdata in real_nodes[i + 1:]:
            if has_edge_between(g, aid, bid):
                continue
            score = shared_tags(adata, bdata)
            if score < min_shared:
                continue
            key = tuple(sorted([aid, bid]))
            if key in seen:
                continue
            seen.add(key)
            shared = sorted(tag_set(adata) & tag_set(bdata))
            results.append({
                "source": aid,
                "target": bid,
                "suggested_type": "analogous-to",
                "confidence": score,
                "reason": f"{score} shared tags: {shared}",
            })
    results.sort(key=lambda r: -r["confidence"])
    return results


# --- Category 4 — Force-fit re-typing ------------------------------------


def force_fit_retype(g: VaultGraph, min_len: int = 60, top_n: int = 20) -> list[dict]:
    """Edges with annotations >min_len chars — annotation may be doing edge-type work."""
    edges = g.annotated_edges(min_annotation_length=min_len)[:top_n]
    results = []
    for e in edges:
        ann_len = len(e.annotation or "")
        hint = e.type
        ann_lower = (e.annotation or "").lower()
        if e.type != "contradicts" and any(
            w in ann_lower
            for w in ("contradicts", "argues against", "tension", "but", "whereas", "ceiling")
        ):
            hint = "contradicts"
        elif e.type == "analogous-to" and any(
            w in ann_lower for w in ("builds", "prerequisite", "foundation", "requires", "depends")
        ):
            hint = "builds-on"
        results.append({
            "source": e.source,
            "target": e.target,
            "current_type": e.type,
            "suggested_type": hint,
            "confidence": ann_len,
            "reason": e.annotation,
        })
    return results


# --- Category 5 — Low-centrality high-substance --------------------------


def low_centrality_high_substance(g: VaultGraph) -> list[dict]:
    """Evergreen notes with PageRank below median — well-developed but under-linked."""
    central = g.most_central(n=9999, by="pagerank")
    scores = {nid: score for nid, score in central}
    v = g.view(collapse=True, include_mentioned=False)
    evergreen = [
        nid for nid, data in v.nodes(data=True)
        if not data.get("_broken")
        and data.get("status") == "evergreen"
        and nid in scores
    ]
    if not evergreen:
        return []
    ev_scores = [scores[nid] for nid in evergreen]
    median_score = statistics.median(ev_scores)
    results = []
    for nid in evergreen:
        score = scores[nid]
        if score < median_score:
            in_deg = v.in_degree(nid)
            out_deg = v.out_degree(nid)
            results.append({
                "source": nid,
                "target": None,
                "suggested_type": None,
                "confidence": round(score, 5),
                "reason": (
                    f"evergreen, PageRank={score:.5f} (below median {median_score:.5f}), "
                    f"in={in_deg} out={out_deg}"
                ),
            })
    results.sort(key=lambda r: r["confidence"])
    return results


# --- Unified entry point -------------------------------------------------

CATEGORY_FNS = {
    "orphan_rescue": orphan_rescue,
    "missing_bidir": missing_bidir,
    "tag_cluster_gaps": lambda g: tag_cluster_gaps(g, min_shared=3),
    "force_fit_retype": lambda g: force_fit_retype(g, min_len=60, top_n=20),
    "low_centrality_high_substance": low_centrality_high_substance,
}


def connect_suggest(
    graph: VaultGraph,
    categories: list[str] | None = None,
) -> dict:
    """Run requested suggestion categories. Read-only.

    Args:
        graph: a loaded VaultGraph
        categories: subset of CATEGORY_FNS keys; None = all

    Returns:
        dict mapping category name → list of suggestion dicts
    """
    requested = categories or list(CATEGORY_FNS.keys())
    out: dict[str, list[dict]] = {}
    for cat in requested:
        fn = CATEGORY_FNS.get(cat)
        if fn is None:
            continue
        out[cat] = fn(graph)
    return out
