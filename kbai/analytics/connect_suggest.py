"""Stage 0: pure-read analytics over the vault graph.

Re-exports the five suggestion functions from vault_connect_suggest.py and
provides a single `connect_suggest(graph, categories=None)` entry point that
returns ranked candidates by category. Never writes to the vault — write
application is the Write Agent's job (Stage 3).

Stage 1 will move the actual implementations into this file; for now we
re-import to avoid 400 lines of churn during scaffolding.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_vault_root))

from vault_connect_suggest import (  # noqa: E402
    orphan_rescue,
    missing_bidir,
    tag_cluster_gaps,
    force_fit_retype,
    low_centrality_high_substance,
)
from vault_graph_loader import VaultGraph  # noqa: E402

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
    """Run requested suggestion categories over the graph. Read-only.

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
