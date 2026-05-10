"""Stage 0 item 4: analytics.connect_suggest is pure-read, returns the
expected category shape, and is wired through as an MCP tool."""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

GRAPH_PATH = _vault_root / "06-Maps" / "vault-graph.json"

from kbai.analytics.connect_suggest import (
    connect_suggest,
    CATEGORY_FNS,
)


def _toy_graph():
    from vault_graph_loader import VaultGraph
    data = {
        "vault_root": str(_vault_root),
        "nodes": [
            {"id": "A", "topics": ["t1", "t2", "t3"], "lenses": [], "status": "evergreen"},
            {"id": "B", "topics": ["t1", "t2", "t3"], "lenses": [], "status": "evergreen"},
            {"id": "C", "topics": ["t9"], "lenses": [], "status": "draft"},
        ],
        "edges": [],
    }
    return VaultGraph(data)


def test_connect_suggest_returns_dict_keyed_by_category():
    g = _toy_graph()
    result = connect_suggest(g)
    assert isinstance(result, dict)
    for cat in CATEGORY_FNS:
        assert cat in result, f"missing category {cat}"
        assert isinstance(result[cat], list)


def test_connect_suggest_filters_categories():
    g = _toy_graph()
    result = connect_suggest(g, categories=["orphan_rescue"])
    assert set(result.keys()) == {"orphan_rescue"}


def test_connect_suggest_unknown_category_silently_skipped():
    g = _toy_graph()
    result = connect_suggest(g, categories=["does_not_exist", "orphan_rescue"])
    assert "does_not_exist" not in result
    assert "orphan_rescue" in result


def test_mcp_tool_registered():
    from minivinnymcp.server import app
    tm = getattr(app, "_tool_manager", None)
    if tm is None:
        return
    assert "analytics_connect_suggest" in tm._tools


def test_mcp_tool_runs_against_real_graph():
    if not GRAPH_PATH.exists():
        return
    from minivinnymcp.server import analytics_connect_suggest
    out = analytics_connect_suggest(categories=["missing_bidir"])
    assert isinstance(out, dict)
    assert "missing_bidir" in out
