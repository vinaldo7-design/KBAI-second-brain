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
    """MultiDiGraph wrapper with vault-specific queries."""

    def __init__(self, data: dict, include_mentioned: bool = False):
        self.data = data
        self.include_mentioned = include_mentioned
        self.G: nx.MultiDiGraph = nx.MultiDiGraph()

        vault_root = Path(data.get("vault_root", "."))
        _taxonomy = load_taxonomy(vault_root)
        _edge_types = _taxonomy.get("edge_types", {})
        self.taxonomy_weights: dict[str, float] = {
            et: float(meta.get("default_weight", 1.0))
            for et, meta in _edge_types.items()
        }
        _collapse_map: dict[str, str] = {
            et: meta["collapse_to"]
            for et, meta in _edge_types.items()
            if meta.get("collapse_to")
        }

        for node in data["nodes"]:
            self.G.add_node(node["id"], **node)

        for edge in data["edges"]:
            if not include_mentioned and edge["type"] == "mentioned":
                continue

            src = edge["source"]
            tgt = edge["target"]
            etype = edge["type"]
            target_exists = edge.get("target_exists", True)

            if etype in _collapse_map:
                src, tgt = tgt, src
                etype = _collapse_map[etype]
                target_exists = True  # new target is original source, always present

            # Dangling target (broken edge) — add marker node so traversal still works.
            if not target_exists:
                if tgt not in self.G:
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
    ) -> list[EdgeResult]:
        """Return typed edges incident to this note."""
        if note_id not in self.G:
            return []
        results: list[EdgeResult] = []
        if direction in ("out", "both"):
            for _, target, data in self.G.out_edges(note_id, data=True):
                if edge_type and data.get("type") != edge_type:
                    continue
                results.append(EdgeResult(
                    source=note_id, target=target,
                    type=data.get("type"), annotation=data.get("annotation"),
                    target_exists=data.get("target_exists", True),
                ))
        if direction in ("in", "both"):
            for source, _, data in self.G.in_edges(note_id, data=True):
                if edge_type and data.get("type") != edge_type:
                    continue
                results.append(EdgeResult(
                    source=source, target=note_id,
                    type=data.get("type"), annotation=data.get("annotation"),
                    target_exists=data.get("target_exists", True),
                ))
        return results

    # --- Centrality ----------------------------------------------------

    def _simple_digraph(self) -> nx.DiGraph:
        """Collapse the multigraph into a weighted DiGraph for centrality."""
        simple = nx.DiGraph()
        for source, target, _ in self.G.edges(data=True):
            if simple.has_edge(source, target):
                simple[source][target]["weight"] += 1
            else:
                simple.add_edge(source, target, weight=1)
        for node in self.G.nodes:
            if node not in simple:
                simple.add_node(node)
        return simple

    def most_central(
        self, n: int = 10, by: str = "pagerank",
    ) -> list[tuple[str, float]]:
        """Top-n nodes by centrality measure."""
        simple = self._simple_digraph()

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
    ) -> Optional[list[str]]:
        """Shortest directed path between two notes, optionally restricted to edge types."""
        if from_note not in self.G or to_note not in self.G:
            return None
        if edge_types:
            sub = nx.DiGraph()
            for source, target, data in self.G.edges(data=True):
                if data.get("type") in edge_types:
                    sub.add_edge(source, target)
            try:
                return nx.shortest_path(sub, from_note, to_note)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None
        simple = nx.DiGraph()
        for s, t in self.G.edges():
            simple.add_edge(s, t)
        try:
            return nx.shortest_path(simple, from_note, to_note)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    # --- Distribution and diagnostics ----------------------------------

    def edge_distribution(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, _, data in self.G.edges(data=True):
            t = data.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def orphans(self) -> list[str]:
        """Notes with zero in-degree and zero out-degree (typed edges only)."""
        return sorted([
            n for n in self.G.nodes
            if not self.G.nodes[n].get("_broken")
            and self.G.in_degree(n) == 0
            and self.G.out_degree(n) == 0
        ])

    def annotated_edges(
        self,
        edge_type: Optional[str] = None,
        min_annotation_length: int = 40,
    ) -> list[EdgeResult]:
        """Edges whose annotations are long — candidates where the annotation is
        doing semantic work the edge type isn't. Force-fit diagnostic."""
        results = []
        for source, target, data in self.G.edges(data=True):
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
