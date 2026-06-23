"""Phase 2b: query-time view semantics + parity with the pre-2b loader.

Three concerns:
  1. Raw view (collapse=False) exposes builds-toward edges with their true
     native count and includes mentioned edges when requested.
  2. The default view (collapse=True, include_mentioned=False) reproduces
     PageRank / PPR scores byte-for-byte against a FROZEN structural graph
     fixture (decoupled from the live vault — see GRAPH_PATH).
  3. missing_bidir now checks native reverse types — no false positives.
  4. _frontier_nodes uses native types: no incoming builds-toward AND no
     outgoing builds-on.
"""

import json
import math
import os
import sys
from pathlib import Path

import networkx as nx

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from vault_graph_loader import VaultGraph

# Parity is checked against a FROZEN structural graph fixture (note ids + edge
# topology, all prose stripped), NOT the live vault graph — so adding/renaming/
# migrating notes never breaks these tests. They guard the loader's
# PPR/PageRank/collapse logic; regenerate the fixture only when that logic
# *intentionally* changes, never to chase a corpus change.
GRAPH_PATH = Path(__file__).parent / "fixtures" / "parity_graph.json"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ppr_baseline.json"


def _graph_available() -> bool:
    return GRAPH_PATH.exists() and FIXTURE_PATH.exists()


# --- (1) raw view exposes native types -----------------------------------


def _bidir_graph_data():
    """A builds-toward B (native). Plus a mentioned edge for B → C."""
    return {
        "vault_root": str(_vault_root),
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "edges": [
            {"source": "A", "target": "B", "type": "builds-toward", "target_exists": True},
            {"source": "B", "target": "C", "type": "mentioned", "target_exists": True},
        ],
    }


def test_raw_view_preserves_builds_toward():
    g = VaultGraph(_bidir_graph_data())
    raw = g.view(collapse=False, include_mentioned=True)
    edge_types = sorted(d.get("type") for _, _, d in raw.edges(data=True))
    assert edge_types == ["builds-toward", "mentioned"]


def test_default_view_collapses_builds_toward_to_builds_on_reversed():
    g = VaultGraph(_bidir_graph_data())
    v = g.view(collapse=True, include_mentioned=False)
    # The A builds-toward B edge becomes a B builds-on A edge.
    edges = [(s, t, d.get("type")) for s, t, d in v.edges(data=True)]
    assert ("B", "A", "builds-on") in edges
    # And mentioned is gone in the default view.
    assert not any(d == "mentioned" for _, _, d in edges)


def test_raw_view_includes_mentioned_when_requested():
    g = VaultGraph(_bidir_graph_data())
    raw_no_mention = g.view(collapse=False, include_mentioned=False)
    raw_with_mention = g.view(collapse=False, include_mentioned=True)
    assert raw_with_mention.number_of_edges() == raw_no_mention.number_of_edges() + 1


# --- (2) PageRank / PPR parity against the fixture ------------------------


def test_pagerank_parity_against_pre_2b_fixture():
    if not _graph_available():
        return
    fixture = json.loads(FIXTURE_PATH.read_text())
    expected = fixture["pagerank"]

    g = VaultGraph.load(str(GRAPH_PATH))
    scores = nx.pagerank(
        g._simple_digraph(collapse=True, include_mentioned=False),
        weight="weight",
    )

    assert set(scores.keys()) == set(expected.keys()), "node sets differ"
    for nid, exp in expected.items():
        got = scores[nid]
        assert math.isclose(got, exp, rel_tol=1e-9, abs_tol=1e-12), \
            f"PageRank mismatch at {nid}: expected {exp}, got {got}"


def test_ppr_parity_single_seed():
    if not _graph_available():
        return
    fixture = json.loads(FIXTURE_PATH.read_text())
    expected = fixture["ppr_mastery_trap"]

    g = VaultGraph.load(str(GRAPH_PATH))
    got = g.ppr_expand({"mastery-trap": 1.0})

    assert set(got.keys()) == set(expected.keys())
    for nid, exp in expected.items():
        assert math.isclose(got[nid], exp, rel_tol=1e-9, abs_tol=1e-12), \
            f"PPR mismatch at {nid}: expected {exp}, got {got[nid]}"


def test_ppr_parity_multi_seed():
    if not _graph_available():
        return
    fixture = json.loads(FIXTURE_PATH.read_text())
    expected = fixture["ppr_two_seed"]

    g = VaultGraph.load(str(GRAPH_PATH))
    got = g.ppr_expand({"governance-capital-day1": 1.0, "schumacher-principle": 0.8})

    for nid, exp in expected.items():
        assert math.isclose(got[nid], exp, rel_tol=1e-9, abs_tol=1e-12), \
            f"PPR mismatch at {nid}"


def test_ppr_parity_standard_exclude():
    if not _graph_available():
        return
    fixture = json.loads(FIXTURE_PATH.read_text())
    expected = fixture["ppr_standard_exclude"]

    g = VaultGraph.load(str(GRAPH_PATH))
    got = g.ppr_expand(
        {"mastery-trap": 1.0}, exclude_types={"contradicts", "mentioned"}
    )

    for nid, exp in expected.items():
        assert math.isclose(got[nid], exp, rel_tol=1e-9, abs_tol=1e-12), \
            f"PPR mismatch at {nid}"


def test_edge_counts_parity():
    if not _graph_available():
        return
    fixture = json.loads(FIXTURE_PATH.read_text())
    g = VaultGraph.load(str(GRAPH_PATH))
    stats = g.graph_stats()
    # graph_counts (default view) should match pre-2b graph_counts.
    assert dict(stats["graph_counts"]) == fixture["graph_counts"]
    # raw_counts (self.G post-construction) should match pre-2b raw counts
    # from data["edges"] — same source data.
    assert dict(stats["raw_counts"]) == fixture["raw_counts"]


# --- (3) missing_bidir on native types -----------------------------------


def _missing_bidir_graph_data():
    """Three pairs:
       1. (P, Q): A builds-on B exists; reverse B builds-toward A missing → flag.
       2. (R, S): R builds-on S AND S builds-toward R both exist → not flagged.
       3. (X, Y): X builds-toward Y exists; reverse Y builds-on X missing → flag.
    """
    return {
        "vault_root": str(_vault_root),
        "nodes": [{"id": n} for n in ("P", "Q", "R", "S", "X", "Y")],
        "edges": [
            {"source": "P", "target": "Q", "type": "builds-on", "target_exists": True},
            {"source": "R", "target": "S", "type": "builds-on", "target_exists": True},
            {"source": "S", "target": "R", "type": "builds-toward", "target_exists": True},
            {"source": "X", "target": "Y", "type": "builds-toward", "target_exists": True},
        ],
    }


def test_missing_bidir_native_no_false_positive_for_complete_pair():
    from kbai.analytics.connect_suggest import missing_bidir
    g = VaultGraph(_missing_bidir_graph_data())
    out = missing_bidir(g)
    suggested = {(r["source"], r["target"], r["suggested_type"]) for r in out}
    # R↔S is complete in source — must NOT appear.
    assert ("S", "R", "builds-toward") not in suggested
    assert ("R", "S", "builds-on") not in suggested


def test_missing_bidir_native_flags_missing_reverse_in_both_directions():
    from kbai.analytics.connect_suggest import missing_bidir
    g = VaultGraph(_missing_bidir_graph_data())
    out = missing_bidir(g)
    suggested = {(r["source"], r["target"], r["suggested_type"]) for r in out}
    # P builds-on Q present, Q builds-toward P missing → flag.
    assert ("Q", "P", "builds-toward") in suggested
    # X builds-toward Y present, Y builds-on X missing → flag.
    assert ("Y", "X", "builds-on") in suggested


# --- (4) _frontier_nodes native semantics --------------------------------


def _frontier_graph_data():
    """Cluster {A, B, C, D}:
       A builds-on B            → A has outgoing builds-on, NOT frontier
       C builds-toward D        → D has incoming builds-toward, NOT frontier
       (B and C have neither outgoing builds-on nor incoming builds-toward)
    """
    return {
        "vault_root": str(_vault_root),
        "nodes": [{"id": n, "title": n} for n in ("A", "B", "C", "D")],
        "edges": [
            {"source": "A", "target": "B", "type": "builds-on", "target_exists": True},
            {"source": "C", "target": "D", "type": "builds-toward", "target_exists": True},
        ],
    }


def test_frontier_nodes_native_semantics():
    from kbai.imagination.signature import _frontier_nodes
    g = VaultGraph(_frontier_graph_data())
    cluster = {"A", "B", "C", "D"}
    out = _frontier_nodes(g, cluster, edges=[], top_n=10)
    frontier_ids = {item["note_id"] for item in out}
    # A excluded: outgoing builds-on.
    # D excluded: incoming builds-toward.
    # B, C are pure frontier.
    assert frontier_ids == {"B", "C"}
