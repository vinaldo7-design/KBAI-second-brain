#!/usr/bin/env python3
"""vault_graph_loader.py — load vault-graph.json into a queryable networkx graph.

The graph JSON produced by vault_graph.py is flat. This module loads it into
a MultiDiGraph and exposes the primitive operations a second-brain needs:
neighbours, centrality, paths, distribution, orphans, force-fit audit.

USAGE AS MODULE
---------------
    from vault_graph_loader import VaultGraph
    g = VaultGraph.load('06-Maps/vault-graph.json')
    g.neighbours('mastery-trap', edge_type='builds-on')
    g.most_central(10, by='pagerank')
    g.path('mastery-trap', 'schumacher-principle')

USAGE AS CLI
------------
Run from vault root (assumes 06-Maps/vault-graph.json):

    python3 vault_graph_loader.py summary <note-id>
    python3 vault_graph_loader.py neighbours <note-id> [--type=TYPE] [--direction=out|in|both]
    python3 vault_graph_loader.py central [N] [--by=pagerank|degree|in_degree|out_degree|betweenness]
    python3 vault_graph_loader.py path <from> <to> [--types=t1,t2]
    python3 vault_graph_loader.py distribution
    python3 vault_graph_loader.py orphans
    python3 vault_graph_loader.py audit [--type=TYPE] [--min-length=N]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import networkx as nx
import yaml


DEFAULT_GRAPH_PATH = "06-Maps/vault-graph.json"


def load_taxonomy(vault_root: Path) -> dict:
    """Load vault_taxonomy.yaml. Returns empty dict if not found."""
    taxonomy_path = vault_root / "vault_taxonomy.yaml"
    if not taxonomy_path.exists():
        return {}
    with open(taxonomy_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class EdgeResult:
    source: str
    target: str
    type: str
    annotation: Optional[str]
    target_exists: bool

    def __str__(self):
        ann = f" — {self.annotation}" if self.annotation else ""
        arrow = "->" if self.target_exists else "~>"  # ~> indicates broken
        return f"[{self.type:14s}] {self.source} {arrow} {self.target}{ann}"


class VaultGraph:
    """MultiDiGraph wrapper with vault-specific queries.

    Construction preserves every edge in its native form: no collapse, no
    mentioned-filter, no reversal. Transforms (collapse_to from the yaml,
    mentioned-filter) happen at query time via `view(collapse, include_mentioned)`.

    Defaults across query methods are `collapse=True, include_mentioned=False`
    so existing call-sites behave identically to the pre-2b loader.
    """

    def __init__(self, data: dict):
        self.data = data
        self.G: nx.MultiDiGraph = nx.MultiDiGraph()

        vault_root = Path(data.get("vault_root", "."))
        _taxonomy = load_taxonomy(vault_root)
        _edge_types = _taxonomy.get("edge_types", {})
        self.taxonomy_weights: dict[str, float] = {
            et: float(meta.get("default_weight", 1.0))
            for et, meta in _edge_types.items()
        }
        self._collapse_map: dict[str, str] = {
            et: meta["collapse_to"]
            for et, meta in _edge_types.items()
            if meta.get("collapse_to")
        }
        self._view_cache: dict[tuple[bool, bool], nx.MultiDiGraph] = {}

        for node in data["nodes"]:
            self.G.add_node(node["id"], **node)

        for edge in data["edges"]:
            src = edge["source"]
            tgt = edge["target"]
            etype = edge["type"]
            target_exists = edge.get("target_exists", True)

            if not target_exists and tgt not in self.G:
                self.G.add_node(tgt, id=tgt, _broken=True)

            self.G.add_edge(
                src, tgt,
                type=etype,
                annotation=edge.get("annotation"),
                target_exists=target_exists,
            )

    @classmethod
    def load(cls, path: str = DEFAULT_GRAPH_PATH, **kwargs) -> "VaultGraph":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f), **kwargs)

    # --- Views ---------------------------------------------------------

    def view(
        self,
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> nx.MultiDiGraph:
        """Cached MultiDiGraph view of self.G with the requested transforms.

        collapse=True applies yaml-declared collapse_to rules (reverses
        source/target and relabels the edge type).
        include_mentioned=False drops `mentioned` edges from the view.

        Defaults reproduce the pre-2b loader's constructed-graph semantics
        byte-for-byte: collapsed + no mentioned.
        """
        key = (collapse, include_mentioned)
        cached = self._view_cache.get(key)
        if cached is not None:
            return cached

        view = nx.MultiDiGraph()
        # Carry non-broken nodes from self.G unconditionally. Broken-target
        # marker nodes are only added when an edge in *this view* targets them
        # — matches pre-2b semantics where broken markers only existed for
        # edges that survived the construction-time filter.
        for nid, ndata in self.G.nodes(data=True):
            if not ndata.get("_broken"):
                view.add_node(nid, **ndata)

        for src, tgt, edata in self.G.edges(data=True):
            etype = edata.get("type")
            if not include_mentioned and etype == "mentioned":
                continue
            target_exists = edata.get("target_exists", True)

            if collapse and etype in self._collapse_map:
                src, tgt = tgt, src
                etype = self._collapse_map[etype]
                target_exists = True  # new target is original source, always present

            if not target_exists and tgt not in view:
                view.add_node(tgt, id=tgt, _broken=True)

            view.add_edge(
                src, tgt,
                type=etype,
                annotation=edata.get("annotation"),
                target_exists=target_exists,
            )

        self._view_cache[key] = view
        return view

    # --- Node access ---------------------------------------------------

    def node(self, note_id: str) -> Optional[dict]:
        return self.G.nodes.get(note_id)

    def summary(self, note_id: str) -> Optional[str]:
        n = self.node(note_id)
        return n.get("summary") if n else None

    def exists(self, note_id: str) -> bool:
        return note_id in self.G and not self.G.nodes[note_id].get("_broken")

    # --- Neighbourhood -------------------------------------------------

    def neighbours(
        self,
        note_id: str,
        edge_type: Optional[str] = None,
        direction: Literal["out", "in", "both"] = "both",
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> list[EdgeResult]:
        """Return typed edges incident to this note."""
        if note_id not in self.G:
            return []
        v = self.view(collapse=collapse, include_mentioned=include_mentioned)
        if note_id not in v:
            return []
        results: list[EdgeResult] = []
        if direction in ("out", "both"):
            for _, target, data in v.out_edges(note_id, data=True):
                if edge_type and data.get("type") != edge_type:
                    continue
                results.append(EdgeResult(
                    source=note_id, target=target,
                    type=data.get("type"), annotation=data.get("annotation"),
                    target_exists=data.get("target_exists", True),
                ))
        if direction in ("in", "both"):
            for source, _, data in v.in_edges(note_id, data=True):
                if edge_type and data.get("type") != edge_type:
                    continue
                results.append(EdgeResult(
                    source=source, target=note_id,
                    type=data.get("type"), annotation=data.get("annotation"),
                    target_exists=data.get("target_exists", True),
                ))
        return results

    # --- Centrality ----------------------------------------------------

    def _simple_digraph(
        self,
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> nx.DiGraph:
        """Flatten the requested view's multi-edges into a weighted DiGraph
        for centrality. Defaults reproduce pre-2b behaviour."""
        v = self.view(collapse=collapse, include_mentioned=include_mentioned)
        simple = nx.DiGraph()
        for source, target, _ in v.edges(data=True):
            if simple.has_edge(source, target):
                simple[source][target]["weight"] += 1
            else:
                simple.add_edge(source, target, weight=1)
        for node in v.nodes:
            if node not in simple:
                simple.add_node(node)
        return simple

    def most_central(
        self,
        n: int = 10,
        by: str = "pagerank",
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> list[tuple[str, float]]:
        """Top-n nodes by centrality measure."""
        simple = self._simple_digraph(collapse=collapse, include_mentioned=include_mentioned)

        if by == "pagerank":
            scores = nx.pagerank(simple, weight="weight")
        elif by == "degree":
            scores = {node: simple.degree(node) for node in simple}
        elif by == "in_degree":
            scores = {node: simple.in_degree(node) for node in simple}
        elif by == "out_degree":
            scores = {node: simple.out_degree(node) for node in simple}
        elif by == "betweenness":
            scores = nx.betweenness_centrality(simple)
        else:
            raise ValueError(f"Unknown centrality measure: {by}")

        # Exclude broken/dangling target nodes from ranking
        scores = {
            k: v for k, v in scores.items()
            if not self.G.nodes[k].get("_broken")
        }
        return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:n]

    # --- Paths ---------------------------------------------------------

    def path(
        self,
        from_note: str,
        to_note: str,
        edge_types: Optional[list[str]] = None,
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> Optional[list[str]]:
        """Shortest directed path between two notes, optionally restricted to edge types."""
        if from_note not in self.G or to_note not in self.G:
            return None
        v = self.view(collapse=collapse, include_mentioned=include_mentioned)
        if edge_types:
            sub = nx.DiGraph()
            for source, target, data in v.edges(data=True):
                if data.get("type") in edge_types:
                    sub.add_edge(source, target)
            try:
                return nx.shortest_path(sub, from_note, to_note)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None
        simple = nx.DiGraph()
        for s, t in v.edges():
            simple.add_edge(s, t)
        try:
            return nx.shortest_path(simple, from_note, to_note)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    # --- Distribution and diagnostics ----------------------------------

    def edge_distribution(
        self,
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> dict[str, int]:
        v = self.view(collapse=collapse, include_mentioned=include_mentioned)
        counts: dict[str, int] = {}
        for _, _, data in v.edges(data=True):
            t = data.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def graph_stats(self) -> dict:
        """Raw (post-construction self.G, native types, mentioned included) vs
        default-view counts (collapsed, mentioned excluded — what queries see).
        Audit tool: reads self.G directly and the default view directly."""
        yaml_types = list(self.taxonomy_weights.keys())  # yaml insertion order

        raw_counts: Counter[str] = Counter()
        for _, _, data in self.G.edges(data=True):
            raw_counts[data.get("type", "unknown")] += 1

        default_view = self.view(collapse=True, include_mentioned=False)
        graph_counts: Counter[str] = Counter()
        for _, _, data in default_view.edges(data=True):
            graph_counts[data.get("type", "unknown")] += 1

        drift = sorted(
            (set(raw_counts) | set(graph_counts)) - set(yaml_types)
        )
        return {
            "total_nodes": self.G.number_of_nodes(),
            "total_edges_raw": self.G.number_of_edges(),
            "total_edges_graph": default_view.number_of_edges(),
            "yaml_types": yaml_types,
            "raw_counts": raw_counts,
            "graph_counts": graph_counts,
            "drift_not_in_yaml": drift,
        }

    def orphans(
        self,
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> list[str]:
        """Notes with zero in-degree and zero out-degree in the requested view."""
        v = self.view(collapse=collapse, include_mentioned=include_mentioned)
        return sorted([
            n for n in v.nodes
            if not v.nodes[n].get("_broken")
            and v.in_degree(n) == 0
            and v.out_degree(n) == 0
        ])

    def ppr_expand(
        self,
        seed_scores: dict[str, float],
        alpha: float = 0.85,
        exclude_types: set[str] | None = None,
        weight_overrides: dict[str, float] | None = None,
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> dict[str, float]:
        """Personalized PageRank seeded by seed_scores (note_id → weight).
        Builds a weighted DiGraph from taxonomy weights, runs PPR, returns
        scores normalised 0–1.

        Args:
            seed_scores: note_id → personalization weight
            alpha: PPR damping
            exclude_types: edge types gated out of the walk entirely
            weight_overrides: edge type → multiplier applied on top of the
                taxonomy weight. Used by cognitive profiles (Stage 5.5+).
            collapse, include_mentioned: select the graph view to walk over.
                Defaults match the pre-2b loader's constructed-graph semantics.
        """
        exclude_types = exclude_types or set()
        weight_overrides = weight_overrides or {}
        v = self.view(collapse=collapse, include_mentioned=include_mentioned)

        simple = nx.DiGraph()
        for node in v.nodes:
            simple.add_node(node)
        for source, target, data in v.edges(data=True):
            etype = data.get("type", "untyped")
            if etype in exclude_types:
                continue
            base_w = self.taxonomy_weights.get(etype, 1.0)
            w = base_w * float(weight_overrides.get(etype, 1.0))
            if simple.has_edge(source, target):
                simple[source][target]["weight"] += w
            else:
                simple.add_edge(source, target, weight=w)

        total = sum(seed_scores.values())
        if total > 0:
            personalization = {nid: s / total for nid, s in seed_scores.items()}
            for node in simple.nodes:
                personalization.setdefault(node, 0.0)
        else:
            personalization = None  # uniform PPR fallback

        try:
            scores = nx.pagerank(
                simple, alpha=alpha, personalization=personalization, weight="weight"
            )
        except (nx.PowerIterationFailedConvergence, ZeroDivisionError):
            scores = personalization or {n: 1.0 / len(simple) for n in simple.nodes}

        max_s = max(scores.values()) if scores else 1.0
        return {k: v / (max_s or 1.0) for k, v in scores.items()}

    def path_attributions(
        self,
        seed_ids: list[str],
        target_ids: list[str],
        max_hops: int = 3,
        exclude_types: set[str] | None = None,
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> dict[str, list[dict] | None]:
        """Batch: best semantic path from any seed to each target.
        Uses inverted taxonomy weights as edge costs so high-semantic edges
        (builds-on, analogous-to) are preferred over structural ones.
        exclude_types strips edges that produce plumbing paths, not reasoning chains."""
        exclude_types = exclude_types or {"referenced-in", "untyped", "mentioned"}
        v = self.view(collapse=collapse, include_mentioned=include_mentioned)

        cost_graph = nx.DiGraph()
        for node in v.nodes:
            cost_graph.add_node(node)
        for src, tgt, data in v.edges(data=True):
            etype = data.get("type", "untyped")
            if etype in exclude_types:
                continue
            w = self.taxonomy_weights.get(etype, 1.0)
            cost = 1.0 / w  # invert: high weight → low cost → preferred
            if cost_graph.has_edge(src, tgt):
                cost_graph[src][tgt]["weight"] = min(cost_graph[src][tgt]["weight"], cost)
            else:
                cost_graph.add_edge(src, tgt, weight=cost)

        target_set = set(target_ids)
        best: dict[str, tuple[float, list[str]]] = {}

        for seed_id in seed_ids:
            if seed_id not in cost_graph:
                continue
            try:
                lengths, paths = nx.single_source_dijkstra(
                    cost_graph, seed_id, weight="weight"
                )
            except Exception:
                continue
            for nid, path in paths.items():
                if nid not in target_set or len(path) - 1 > max_hops:
                    continue
                cost = lengths[nid]
                if nid not in best or cost < best[nid][0]:
                    best[nid] = (cost, path)

        output: dict[str, list[dict] | None] = {}
        for nid in target_ids:
            if nid not in best:
                output[nid] = None
                continue
            _, path = best[nid]
            if len(path) < 2:
                output[nid] = None
                continue
            steps = []
            for i in range(len(path) - 1):
                s, t = path[i], path[i + 1]
                edge_type, best_w = "untyped", 0.0
                for _, t2, edata in v.out_edges(s, data=True):
                    if t2 == t:
                        etype = edata.get("type", "untyped")
                        w = self.taxonomy_weights.get(etype, 0.0)
                        if w > best_w:
                            best_w, edge_type = w, etype
                steps.append({"from": s, "edge": edge_type, "to": t})
            output[nid] = steps

        return output

    def annotated_edges(
        self,
        edge_type: Optional[str] = None,
        min_annotation_length: int = 40,
        collapse: bool = True,
        include_mentioned: bool = False,
    ) -> list[EdgeResult]:
        """Edges whose annotations are long — candidates where the annotation is
        doing semantic work the edge type isn't. Force-fit diagnostic."""
        v = self.view(collapse=collapse, include_mentioned=include_mentioned)
        results = []
        for source, target, data in v.edges(data=True):
            ann = data.get("annotation") or ""
            if len(ann) < min_annotation_length:
                continue
            if edge_type and data.get("type") != edge_type:
                continue
            results.append(EdgeResult(
                source=source, target=target,
                type=data.get("type"), annotation=ann,
                target_exists=data.get("target_exists", True),
            ))
        results.sort(key=lambda e: -len(e.annotation or ""))
        return results


# --- CLI -----------------------------------------------------------------

def _print_edges(edges: list[EdgeResult], limit: int = 50):
    for e in edges[:limit]:
        print(f"  {e}")
    if len(edges) > limit:
        print(f"  ... and {len(edges) - limit} more")


def _parse_args(argv: list[str]) -> tuple[list[str], dict[str, str]]:
    pos, kw = [], {}
    for a in argv:
        if a.startswith("--"):
            key, _, val = a[2:].partition("=")
            kw[key.replace("-", "_")] = val
        else:
            pos.append(a)
    return pos, kw


USAGE = """Usage:
  python3 vault_graph_loader.py summary <note-id>
  python3 vault_graph_loader.py neighbours <note-id> [--type=TYPE] [--direction=out|in|both]
  python3 vault_graph_loader.py central [N] [--by=pagerank|degree|in_degree|out_degree|betweenness]
  python3 vault_graph_loader.py path <from> <to> [--types=t1,t2]
  python3 vault_graph_loader.py distribution
  python3 vault_graph_loader.py graph_stats
  python3 vault_graph_loader.py orphans
  python3 vault_graph_loader.py audit [--type=TYPE] [--min-length=N]

Optional for any command:  --graph=PATH  (default: 06-Maps/vault-graph.json)
"""


def main():
    argv = sys.argv[1:]
    if not argv:
        print(USAGE)
        sys.exit(0)

    cmd = argv[0]
    pos, kw = _parse_args(argv[1:])
    graph_path = kw.pop("graph", DEFAULT_GRAPH_PATH)

    if not Path(graph_path).exists():
        print(f"Graph file not found: {graph_path}", file=sys.stderr)
        print("Run vault_graph.py first to generate it.", file=sys.stderr)
        sys.exit(1)

    g = VaultGraph.load(graph_path)

    if cmd == "summary":
        if not pos:
            print("Need a note id.", file=sys.stderr); sys.exit(1)
        s = g.summary(pos[0])
        print(s or f"(no summary for {pos[0]})")

    elif cmd == "neighbours":
        if not pos:
            print("Need a note id.", file=sys.stderr); sys.exit(1)
        note = pos[0]
        edges = g.neighbours(
            note,
            edge_type=kw.get("type"),
            direction=kw.get("direction", "both"),
        )
        header = f"{note} — {len(edges)} edges"
        if kw.get("type"): header += f" [{kw['type']}]"
        header += f" [{kw.get('direction', 'both')}]"
        print(header)
        _print_edges(edges)

    elif cmd == "central":
        n = int(pos[0]) if pos else 10
        by = kw.get("by", "pagerank")
        print(f"Top {n} by {by}:")
        for rank, (node, score) in enumerate(g.most_central(n=n, by=by), 1):
            print(f"  {rank:2}. {node:40s} {score:.4f}")

    elif cmd == "path":
        if len(pos) < 2:
            print("Need <from> <to>.", file=sys.stderr); sys.exit(1)
        edge_types = kw["types"].split(",") if "types" in kw else None
        p = g.path(pos[0], pos[1], edge_types=edge_types)
        if p:
            print(" -> ".join(p))
        else:
            tail = f" via {','.join(edge_types)}" if edge_types else ""
            print(f"No path from {pos[0]} to {pos[1]}{tail}")

    elif cmd == "distribution":
        d = g.edge_distribution()
        total = sum(d.values())
        print(f"Edge distribution ({total} edges):")
        for t, c in d.items():
            print(f"  {t:15s} {c:4}  ({100 * c / total:5.1f}%)")

    elif cmd == "graph_stats":
        s = g.graph_stats()
        print(f"Total nodes (raw self.G): {s['total_nodes']}")
        print(f"Total edges (raw):        {s['total_edges_raw']}")
        print(f"Total edges (graph):      {s['total_edges_graph']}")
        print()
        print("  raw  = self.G — native types, mentioned included, no collapse")
        print("  graph= default view — collapsed, mentioned excluded (what queries see)")
        print()
        print(f"  {'type':18s} {'raw':>6s} {'graph':>6s}")
        print(f"  {'-'*18} {'-'*6} {'-'*6}")
        for t in s["yaml_types"]:
            print(f"  {t:18s} {s['raw_counts'].get(t, 0):6d} {s['graph_counts'].get(t, 0):6d}")
        drift = s["drift_not_in_yaml"]
        print()
        print(f"Edge types in graph/raw but not in vault_taxonomy.yaml (expected 0): {len(drift)}")
        for t in drift:
            print(f"  {t:18s} {s['raw_counts'].get(t, 0):6d} {s['graph_counts'].get(t, 0):6d}")

    elif cmd == "orphans":
        orphs = g.orphans()
        print(f"{len(orphs)} orphan note(s):")
        for o in orphs:
            print(f"  {o}")

    elif cmd == "audit":
        edge_type = kw.get("type")
        min_len = int(kw.get("min_length", 40))
        edges = g.annotated_edges(edge_type=edge_type, min_annotation_length=min_len)
        suffix = f" of type {edge_type}" if edge_type else ""
        print(f"{len(edges)} force-fit candidates (annotation >={min_len} chars){suffix}:")
        _print_edges(edges)

    else:
        print(f"Unknown command: {cmd}")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
