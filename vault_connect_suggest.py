#!/usr/bin/env python3
"""vault_connect_suggest.py — ranked link suggestions for the vault.

Five categories:
  1. Orphan rescue       — zero-typed-edge notes, 3 nearest by shared tags
  2. Missing bidir       — A builds-on B but B has no builds-toward A
  3. Tag-cluster gaps    — share 3+ tags, no direct edge → analogous-to candidate
  4. Force-fit re-type   — annotation >60 chars, edge type may be wrong
  5. Low-centrality high-substance — evergreen notes with PageRank below median

Output: 06-Maps/connect-suggestions.md
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

import networkx as nx

from vault_graph_loader import VaultGraph

GRAPH_PATH = "06-Maps/vault-graph.json"
OUTPUT_PATH = "06-Maps/connect-suggestions.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def shared_tags(a: dict, b: dict) -> int:
    ta = set(a.get("topics", [])) | set(a.get("lenses", []))
    tb = set(b.get("topics", [])) | set(b.get("lenses", []))
    return len(ta & tb)


def tag_set(node: dict) -> set:
    return set(node.get("topics", [])) | set(node.get("lenses", []))


def has_edge_between(g: VaultGraph, a: str, b: str) -> bool:
    return g.G.has_edge(a, b) or g.G.has_edge(b, a)


def typed_degree(g: VaultGraph, node_id: str) -> int:
    count = 0
    for _, _, data in g.G.out_edges(node_id, data=True):
        if data.get("type") not in (None, "untyped", "mentioned"):
            count += 1
    for _, _, data in g.G.in_edges(node_id, data=True):
        if data.get("type") not in (None, "untyped", "mentioned"):
            count += 1
    return count


# ---------------------------------------------------------------------------
# Category 1 — Orphan rescue
# ---------------------------------------------------------------------------

def orphan_rescue(g: VaultGraph) -> list[dict]:
    """For each note with zero typed edges, suggest 3 nearest by shared tags."""
    real_nodes = [
        (nid, data) for nid, data in g.G.nodes(data=True)
        if not data.get("_broken") and data.get("type") not in ("map",)
    ]

    orphans = [(nid, data) for nid, data in real_nodes if typed_degree(g, nid) == 0]
    candidates = [(nid, data) for nid, data in real_nodes]

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


# ---------------------------------------------------------------------------
# Category 2 — Missing bidirectional
# ---------------------------------------------------------------------------

def missing_bidir(g: VaultGraph) -> list[dict]:
    """A builds-on B implies B should have a builds-toward A. Flag if missing."""
    results = []
    seen = set()
    for source, target, data in g.G.edges(data=True):
        etype = data.get("type")
        if etype not in ("builds-on", "builds-toward"):
            continue
        # builds-on A->B means B should have builds-toward->A
        if etype == "builds-on":
            expected_reverse_type = "builds-toward"
            expected_source, expected_target = target, source
        else:
            # builds-toward A->B means B should have builds-on->A
            expected_reverse_type = "builds-on"
            expected_source, expected_target = target, source

        key = (expected_source, expected_target, expected_reverse_type)
        if key in seen:
            continue

        # Check whether the reverse typed edge already exists
        reverse_exists = any(
            d.get("type") == expected_reverse_type
            for _, _, d in g.G.out_edges(expected_source, data=True)
            if _ == expected_source and list(g.G.successors(expected_source))
        )
        # Simpler: iterate directly
        reverse_exists = False
        for _, tgt, d in g.G.out_edges(expected_source, data=True):
            if tgt == expected_target and d.get("type") == expected_reverse_type:
                reverse_exists = True
                break

        if not reverse_exists and g.G.nodes.get(expected_source) and not g.G.nodes[expected_source].get("_broken"):
            seen.add(key)
            results.append({
                "source": expected_source,
                "target": expected_target,
                "suggested_type": expected_reverse_type,
                "confidence": "structural",
                "reason": f"{source} --[{etype}]--> {target} exists; reverse {expected_reverse_type} is missing",
            })
    # Sort: put builds-toward suggestions first (more likely actionable)
    results.sort(key=lambda r: (r["suggested_type"], r["source"]))
    return results


# ---------------------------------------------------------------------------
# Category 3 — Tag-cluster gaps
# ---------------------------------------------------------------------------

def tag_cluster_gaps(g: VaultGraph, min_shared: int = 3) -> list[dict]:
    """Pairs sharing 3+ tags with no direct edge — analogous-to candidates."""
    real_nodes = [
        (nid, data) for nid, data in g.G.nodes(data=True)
        if not data.get("_broken") and data.get("type") not in ("map",)
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


# ---------------------------------------------------------------------------
# Category 4 — Force-fit re-typing
# ---------------------------------------------------------------------------

def force_fit_retype(g: VaultGraph, min_len: int = 60, top_n: int = 20) -> list[dict]:
    """Edges with annotations >min_len chars — annotation may be doing edge-type work."""
    edges = g.annotated_edges(min_annotation_length=min_len)[:top_n]
    results = []
    for e in edges:
        ann_len = len(e.annotation or "")
        # Heuristic: suggest a retype only when the annotation contains
        # contradiction language on a non-contradicts edge, or causal language
        # on an analogous-to edge.
        hint = e.type
        ann_lower = (e.annotation or "").lower()
        if e.type != "contradicts" and any(
            w in ann_lower for w in ("contradicts", "argues against", "tension", "but", "whereas", "ceiling")
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


# ---------------------------------------------------------------------------
# Category 5 — Low-centrality high-substance
# ---------------------------------------------------------------------------

def low_centrality_high_substance(g: VaultGraph) -> list[dict]:
    """Evergreen notes with PageRank below median — well-developed but under-linked."""
    central = g.most_central(n=9999, by="pagerank")
    scores = {nid: score for nid, score in central}

    evergreen = [
        nid for nid, data in g.G.nodes(data=True)
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
            in_deg = g.G.in_degree(nid)
            out_deg = g.G.out_degree(nid)
            results.append({
                "source": nid,
                "target": None,
                "suggested_type": None,
                "confidence": round(score, 5),
                "reason": f"evergreen, PageRank={score:.5f} (below median {median_score:.5f}), "
                          f"in={in_deg} out={out_deg}",
            })
    results.sort(key=lambda r: r["confidence"])
    return results


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def render_markdown(
    orphans: list[dict],
    bidir: list[dict],
    gaps: list[dict],
    retype: list[dict],
    substance: list[dict],
) -> str:
    lines = [
        "# Vault Connect Suggestions",
        "",
        "Auto-generated by `vault_connect_suggest.py`. Five categories of missing links.",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Category | Count |",
        f"|---|---|",
        f"| 1. Orphan rescue | {len(orphans)} |",
        f"| 2. Missing bidirectional | {len(bidir)} |",
        f"| 3. Tag-cluster gaps (3+ shared tags) | {len(gaps)} |",
        f"| 4. Force-fit re-typing (annotation >60 chars) | {len(retype)} |",
        f"| 5. Low-centrality evergreen | {len(substance)} |",
        "",
        "---",
        "",
    ]

    # --- Category 1 ---
    lines += [
        "## 1. Orphan Rescue",
        "",
        "Notes with zero typed edges. Suggestions by shared tag proximity.",
        "",
    ]
    if orphans:
        lines.append("| Note | Suggested link | Type | Shared tags | Reason |")
        lines.append("|---|---|---|---|---|")
        for r in orphans:
            lines.append(f"| `{r['source']}` | `{r['target']}` | {r['suggested_type']} | {r['confidence']} | {r['reason']} |")
    else:
        lines.append("_No orphans with tag matches found._")
    lines.append("")

    # --- Category 2 ---
    lines += [
        "---",
        "",
        "## 2. Missing Bidirectional Edges",
        "",
        "A `builds-on` B implies B should have `builds-toward` A, and vice versa.",
        "",
    ]
    if bidir:
        lines.append("| Add this edge | Type | Because |")
        lines.append("|---|---|---|")
        for r in bidir[:40]:
            lines.append(f"| `{r['source']}` → `{r['target']}` | {r['suggested_type']} | {r['reason']} |")
        if len(bidir) > 40:
            lines.append(f"| _(+{len(bidir) - 40} more)_ | | |")
    else:
        lines.append("_No asymmetries found._")
    lines.append("")

    # --- Category 3 ---
    lines += [
        "---",
        "",
        "## 3. Tag-Cluster Gaps",
        "",
        "Pairs sharing 3+ tags with no direct edge. Strong `analogous-to` candidates.",
        "",
    ]
    if gaps:
        lines.append("| Note A | Note B | Shared tags | Reason |")
        lines.append("|---|---|---|---|")
        for r in gaps[:30]:
            lines.append(f"| `{r['source']}` | `{r['target']}` | {r['confidence']} | {r['reason']} |")
        if len(gaps) > 30:
            lines.append(f"| _(+{len(gaps) - 30} more)_ | | | |")
    else:
        lines.append("_No tag-cluster gaps found._")
    lines.append("")

    # --- Category 4 ---
    lines += [
        "---",
        "",
        "## 4. Force-Fit Re-typing Candidates",
        "",
        "Edges with annotations >60 chars where annotation language suggests a different edge type.",
        "",
    ]
    if retype:
        lines.append("| Source | Target | Current type | Suggested type | Annotation (truncated) |")
        lines.append("|---|---|---|---|---|")
        for r in retype:
            ann = (r["reason"] or "")[:120].replace("|", "\\|")
            flag = " ⚠️" if r["current_type"] != r["suggested_type"] else ""
            lines.append(
                f"| `{r['source']}` | `{r['target']}` | {r['current_type']}{flag} | {r['suggested_type']} | {ann}… |"
            )
    else:
        lines.append("_No force-fit candidates found._")
    lines.append("")

    # --- Category 5 ---
    lines += [
        "---",
        "",
        "## 5. Low-Centrality High-Substance Notes",
        "",
        "Evergreen notes with PageRank below the evergreen median. "
        "Well-developed ideas that aren't yet load-bearing in the graph.",
        "",
    ]
    if substance:
        lines.append("| Note | PageRank | In | Out | Action |")
        lines.append("|---|---|---|---|---|")
        for r in substance:
            parts = r["reason"].split(", ")
            pr = next((p for p in parts if "PageRank" in p), "")
            in_out = [p for p in parts if p.startswith("in=") or p.startswith("out=")]
            in_str = in_out[0] if in_out else ""
            out_str = in_out[1] if len(in_out) > 1 else ""
            lines.append(
                f"| `{r['source']}` | {r['confidence']:.5f} | {in_str.replace('in=','')} | "
                f"{out_str.replace('out=','')} | add incoming `analogous-to` or `builds-toward` links |"
            )
    else:
        lines.append("_No low-centrality evergreen notes found._")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_Generated by `vault_connect_suggest.py`_")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    g = VaultGraph.load(GRAPH_PATH)

    print("Running category 1: orphan rescue…")
    orphans = orphan_rescue(g)

    print("Running category 2: missing bidirectional…")
    bidir = missing_bidir(g)

    print("Running category 3: tag-cluster gaps…")
    gaps = tag_cluster_gaps(g, min_shared=3)

    print("Running category 4: force-fit re-typing…")
    retype = force_fit_retype(g, min_len=60, top_n=20)

    print("Running category 5: low-centrality high-substance…")
    substance = low_centrality_high_substance(g)

    print("\nSummary:")
    print(f"  1. Orphan rescue suggestions:       {len(orphans)}")
    print(f"  2. Missing bidirectional edges:     {len(bidir)}")
    print(f"  3. Tag-cluster gaps:                {len(gaps)}")
    print(f"  4. Force-fit re-type candidates:    {len(retype)}")
    print(f"  5. Low-centrality evergreen notes:  {len(substance)}")

    md = render_markdown(orphans, bidir, gaps, retype, substance)
    Path(OUTPUT_PATH).write_text(md, encoding="utf-8")
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
