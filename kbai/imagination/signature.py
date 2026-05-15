"""Cluster signature extraction — pure read over the vault graph.

A *cluster signature* is a structural fingerprint of the subgraph around a
seed: size, edge-type distribution, load-bearing nodes, terminal frontier,
and dominant vocabulary. This is what the imagination prompts reason over.

Pure functions, dependency-injected graph — testable without
sentence-transformers or a real vault.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from vault_graph_loader import VaultGraph


# Stopwords for thematic-vocabulary extraction. Intentionally small — most
# domain signal lives in nouns that survive frequency filtering anyway.
_STOPWORDS: set[str] = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at",
    "for", "with", "as", "is", "are", "was", "were", "be", "been", "being",
    "by", "from", "that", "this", "these", "those", "it", "its", "not",
    "no", "than", "then", "so", "if", "into", "out", "up", "down", "over",
    "under", "can", "cannot", "must", "may", "might", "would", "could",
    "should", "will", "shall", "have", "has", "had", "do", "does", "did",
    "what", "when", "where", "why", "how", "which", "who", "whom",
    "one", "two", "three", "more", "less", "most", "least", "any", "all",
    "some", "each", "every", "such", "same", "different", "other", "another",
    "also", "only", "even", "just", "still", "ever", "never", "always",
    "often", "sometimes", "thus", "hence", "therefore", "however",
    "i", "we", "you", "they", "he", "she", "his", "her", "their", "our", "your",
    "between", "across", "through", "within", "without", "before", "after",
    "while", "during", "because", "since", "though", "although", "about",
    "vault", "note", "notes", "summary", "title",  # vault-specific noise
}


def _collect_subgraph(
    graph: VaultGraph,
    seed_id: str,
    depth: int,
) -> tuple[set[str], list[tuple[str, str, dict[str, Any]]]]:
    """BFS to depth `depth` from seed_id (both directions). Returns (node_ids,
    edges_inside_subgraph). Skips broken / map-type nodes."""
    if not graph.exists(seed_id):
        return set(), []

    nodes: set[str] = {seed_id}
    frontier: list[str] = [seed_id]
    for _ in range(max(0, depth)):
        next_frontier: list[str] = []
        for n in frontier:
            for e in graph.neighbours(n, direction="both"):
                other = e.target if e.source == n else e.source
                node_data = graph.node(other) or {}
                if node_data.get("_broken"):
                    continue
                if other not in nodes:
                    nodes.add(other)
                    next_frontier.append(other)
        frontier = next_frontier
        if not frontier:
            break

    edges: list[tuple[str, str, dict[str, Any]]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for src in nodes:
        for _, tgt, data in graph.G.out_edges(src, data=True):
            if tgt not in nodes:
                continue
            etype = data.get("type") or "untyped"
            key = (src, tgt, etype)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            edges.append((src, tgt, dict(data)))
    return nodes, edges


def _tokenise(text: str) -> list[str]:
    if not text:
        return []
    return [w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower()) if w not in _STOPWORDS]


def _thematic_vocabulary(
    graph: VaultGraph,
    nodes: set[str],
    top_n: int = 15,
) -> list[tuple[str, int]]:
    """Top-n distinctive words across the cluster's note summaries."""
    counter: Counter[str] = Counter()
    for nid in nodes:
        node = graph.node(nid) or {}
        for field in ("summary", "title"):
            counter.update(_tokenise(node.get(field, "")))
    return counter.most_common(top_n)


def _load_bearing_nodes(
    graph: VaultGraph,
    nodes: set[str],
    edges: list[tuple[str, str, dict[str, Any]]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """High in-degree, low contradicts ratio — concepts the cluster depends on
    but rarely pressure-tests. These are the prime fracture candidates."""
    in_deg: Counter[str] = Counter()
    contradicts_in: Counter[str] = Counter()
    for src, tgt, data in edges:
        etype = data.get("type") or "untyped"
        if etype in ("untyped", "mentioned", "referenced-in"):
            continue
        in_deg[tgt] += 1
        if etype == "contradicts":
            contradicts_in[tgt] += 1

    scored: list[tuple[float, str]] = []
    for nid, deg in in_deg.items():
        if deg < 2:
            continue
        contradiction_ratio = contradicts_in[nid] / deg
        # Score = load it carries × (1 - how pressure-tested it is)
        score = deg * (1.0 - contradiction_ratio)
        scored.append((score, nid))
    scored.sort(key=lambda x: -x[0])

    out: list[dict[str, Any]] = []
    for score, nid in scored[:top_n]:
        node = graph.node(nid) or {}
        out.append({
            "note_id": nid,
            "title": node.get("title"),
            "summary": node.get("summary"),
            "in_degree": in_deg[nid],
            "contradicts_in": contradicts_in[nid],
            "unchallenged_load_score": round(score, 3),
        })
    return out


def _frontier_nodes(
    graph: VaultGraph,
    nodes: set[str],
    edges: list[tuple[str, str, dict[str, Any]]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Terminal frontier — notes with no outgoing builds-on / builds-toward
    inside this cluster. These are where the cluster's reasoning has run
    out of explicit prerequisites; the natural place for `extend` to push."""
    has_builds_out: set[str] = set()
    for src, tgt, data in edges:
        if data.get("type") in ("builds-on", "builds-toward"):
            has_builds_out.add(src)

    frontier_ids = [nid for nid in nodes if nid not in has_builds_out]
    # Stable order: by title for determinism in tests
    frontier_ids.sort(key=lambda n: ((graph.node(n) or {}).get("title") or n))

    out: list[dict[str, Any]] = []
    for nid in frontier_ids[:top_n]:
        node = graph.node(nid) or {}
        out.append({
            "note_id": nid,
            "title": node.get("title"),
            "summary": node.get("summary"),
        })
    return out


def _edge_distribution(edges: list[tuple[str, str, dict[str, Any]]]) -> dict[str, int]:
    dist: Counter[str] = Counter()
    for _, _, data in edges:
        dist[data.get("type") or "untyped"] += 1
    return dict(dist)


def _contradicts_ratio(edge_dist: dict[str, int]) -> float:
    typed_total = sum(
        v for k, v in edge_dist.items()
        if k not in ("untyped", "mentioned", "referenced-in")
    )
    if typed_total == 0:
        return 0.0
    return round(edge_dist.get("contradicts", 0) / typed_total, 3)


def extract_cluster_signature(
    graph: VaultGraph,
    seed_id: str,
    depth: int = 2,
) -> dict[str, Any]:
    """Pure structural fingerprint of the subgraph around seed_id.

    Args:
        graph: a loaded VaultGraph
        seed_id: anchor note id (or map id)
        depth: BFS hops to include (default 2 — wide enough to catch
            adversaries-of-adversaries, narrow enough to stay coherent)

    Returns a dict suitable for ClusterSignature construction.
    """
    if not graph.exists(seed_id):
        return {
            "seed": seed_id,
            "error": f"Note '{seed_id}' not found in graph.",
            "size": 0,
            "depth": depth,
        }

    nodes, edges = _collect_subgraph(graph, seed_id, depth)
    edge_dist = _edge_distribution(edges)
    seed_node = graph.node(seed_id) or {}

    return {
        "seed": seed_id,
        "seed_title": seed_node.get("title"),
        "seed_summary": seed_node.get("summary"),
        "depth": depth,
        "size": len(nodes),
        "edge_distribution": edge_dist,
        "contradicts_ratio": _contradicts_ratio(edge_dist),
        "load_bearing": _load_bearing_nodes(graph, nodes, edges),
        "frontier": _frontier_nodes(graph, nodes, edges),
        "thematic_vocabulary": _thematic_vocabulary(graph, nodes),
        "member_ids": sorted(nodes),
    }
