"""Stage 0 item 3: synthetic graph proves mentioned edges are excluded from
standard/sparring PPR walks but admitted in exhaustive mode."""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from vault_graph_loader import VaultGraph


def _toy_graph_data():
    """A → B (builds-on), A → C (mentioned).
    C is reachable only via mentioned. In a graph loaded with
    include_mentioned=False, C should not appear at all."""
    return {
        "vault_root": str(_vault_root),
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "edges": [
            {"source": "A", "target": "B", "type": "builds-on", "target_exists": True},
            {"source": "A", "target": "C", "type": "mentioned", "target_exists": True},
        ],
    }


def test_mentioned_dropped_in_default_load():
    g = VaultGraph(_toy_graph_data())  # include_mentioned defaults to False
    # The mentioned edge is filtered at construction; A has no out-edge to C.
    a_targets = {t for _, t, _ in g.G.out_edges("A", data=True)}
    assert "C" not in a_targets
    assert "B" in a_targets


def test_mentioned_present_in_exhaustive_load():
    g = VaultGraph(_toy_graph_data(), include_mentioned=True)
    a_targets = {t for _, t, _ in g.G.out_edges("A", data=True)}
    assert "C" in a_targets
    assert "B" in a_targets


def test_ppr_does_not_reach_mentioned_only_node_in_standard():
    g = VaultGraph(_toy_graph_data())
    scores = g.ppr_expand({"A": 1.0})
    # C is not in the graph → not in scores
    assert "C" not in scores or scores["C"] == 0.0


def test_ppr_reaches_mentioned_node_in_exhaustive():
    g = VaultGraph(_toy_graph_data(), include_mentioned=True)
    # Even excluding mentioned at the walk level should leave C orphaned, but
    # exhaustive mode admits it (empty exclude set).
    scores = g.ppr_expand({"A": 1.0}, exclude_types=set())
    assert "C" in scores
    assert scores["C"] > 0.0


def test_ppr_excludes_mentioned_when_walk_filtered():
    """Even with mentioned edges in the graph, gating them at the walk level
    (as standard mode does) should make C unreachable from A."""
    g = VaultGraph(_toy_graph_data(), include_mentioned=True)
    scores = g.ppr_expand({"A": 1.0}, exclude_types={"mentioned"})
    # C now has no inbound edge → score is just the PPR teleport baseline
    # (not zero in absolute terms, but A and B should both score higher).
    assert scores["A"] > scores.get("C", 0.0)
    assert scores["B"] > scores.get("C", 0.0)
