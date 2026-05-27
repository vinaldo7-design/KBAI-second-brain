"""Stage 0 item 3 (re-cast for Phase 2b): mentioned-edge handling is now a
query-time concern. Construction preserves every edge in self.G; the default
view drops mentioned, the include_mentioned=True view keeps them."""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from vault_graph_loader import VaultGraph


def _toy_graph_data():
    """A → B (builds-on), A → C (mentioned).
    C is reachable only via the mentioned edge."""
    return {
        "vault_root": str(_vault_root),
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "edges": [
            {"source": "A", "target": "B", "type": "builds-on", "target_exists": True},
            {"source": "A", "target": "C", "type": "mentioned", "target_exists": True},
        ],
    }


def test_construction_preserves_mentioned_in_raw_graph():
    g = VaultGraph(_toy_graph_data())
    a_targets = {t for _, t, _ in g.G.out_edges("A", data=True)}
    assert "B" in a_targets
    assert "C" in a_targets  # mentioned edge stored at construction


def test_default_view_drops_mentioned():
    g = VaultGraph(_toy_graph_data())
    v = g.view(collapse=True, include_mentioned=False)
    a_targets = {t for _, t, _ in v.out_edges("A", data=True)}
    assert "B" in a_targets
    assert "C" not in a_targets


def test_mentioned_view_includes_mentioned():
    g = VaultGraph(_toy_graph_data())
    v = g.view(collapse=True, include_mentioned=True)
    a_targets = {t for _, t, _ in v.out_edges("A", data=True)}
    assert "B" in a_targets
    assert "C" in a_targets


def test_ppr_default_does_not_reach_mentioned_only_node():
    g = VaultGraph(_toy_graph_data())
    scores = g.ppr_expand({"A": 1.0})
    # Default view excludes mentioned → C unreachable from A
    assert scores["A"] > scores.get("C", 0.0)
    assert scores["B"] > scores.get("C", 0.0)


def test_ppr_with_include_mentioned_reaches_mentioned_node():
    g = VaultGraph(_toy_graph_data())
    scores = g.ppr_expand({"A": 1.0}, include_mentioned=True, exclude_types=set())
    assert "C" in scores
    assert scores["C"] > 0.0


def test_ppr_include_mentioned_but_excluded_at_walk_level():
    """When mentioned edges are loaded into the view but explicitly excluded
    at the walk level, C drops out of reachability again."""
    g = VaultGraph(_toy_graph_data())
    scores = g.ppr_expand(
        {"A": 1.0}, include_mentioned=True, exclude_types={"mentioned"}
    )
    assert scores["A"] > scores.get("C", 0.0)
    assert scores["B"] > scores.get("C", 0.0)
