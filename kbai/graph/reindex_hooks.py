"""Incremental graph-edge reindex hook — REAL (graph-side freshness).

Previously a stub. Now, given a note_id, it re-parses just that one note and
merges the result into 06-Maps/vault-graph.json WITHOUT walking the whole vault:
its node + outgoing edges are replaced, and every edge's `target_exists` is
recomputed against the updated node set (so creating a note resolves edges that
were dangling to it). The result equals a full `vault_graph.build_graph` for the
graph's nodes + edges — verified by a parity test.

Mirrors the embed-on-write hook: lazy, fail-soft (every failure returns a status
dict, never raises), so a hook failure can't break the write path. The graph's
`validation` diagnostics block is left as-is (refreshed by the next full
rebuild); retrieval/PPR read nodes + edges, not validation.

Contract: accepts a single note_id (+ optional vault_root). MUST NOT call
vault_graph.build_graph or otherwise walk the whole vault.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_vault_root(vault_root) -> Path:
    """Explicit arg > $VAULT_ROOT > module-relative (kbai/graph/ -> repo root)."""
    if vault_root:
        return Path(vault_root)
    if env := os.environ.get("VAULT_ROOT"):
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


def update_note_edges(note_id: str, vault_root=None) -> dict:
    """Reparse one note and merge its node + edges into the live graph JSON.
    Returns a status dict; NEVER raises (the write path swallows failures)."""
    if not isinstance(note_id, str) or not note_id:
        return {"status": "error", "error": "note_id required"}

    try:
        root = _resolve_vault_root(vault_root)
        graph_path = root / "06-Maps" / "vault-graph.json"
        if not graph_path.exists():
            logger.info("reindex_edges: no graph yet note=%s", note_id)
            return {"status": "skipped", "note_id": note_id, "reason": "no_graph"}

        import vault_graph  # lazy: heavy module, only needed on a real write
        from kbai.storage.note_io import find_note_file

        note_path = find_note_file(note_id, root)
        if note_path is None:
            logger.warning("reindex_edges: note file not found note=%s", note_id)
            return {"status": "skipped", "note_id": note_id, "reason": "note_file_not_found"}

        typed_sections, untyped_sections, _ = vault_graph.load_taxonomy(root)
        node, edges, _issues = vault_graph.parse_note(
            note_path, root, typed_sections, untyped_sections
        )

        graph = json.loads(graph_path.read_text(encoding="utf-8"))

        # Replace this note's node + its OUTGOING edges; keep everyone else's.
        nodes = [n for n in graph["nodes"] if n.get("id") != note_id]
        nodes.append(asdict(node))
        merged_edges = [e for e in graph["edges"] if e.get("source") != note_id]
        merged_edges.extend(asdict(e) for e in edges)

        # Recompute target_exists against the updated node set — mirrors
        # vault_graph.validate(). Creating this note resolves edges dangling to it.
        node_ids = {n["id"] for n in nodes}
        for e in merged_edges:
            e["target_exists"] = e["target"] in node_ids

        graph["nodes"] = nodes
        graph["edges"] = merged_edges
        graph_path.write_text(
            json.dumps(graph, default=vault_graph._json_default, indent=2),
            encoding="utf-8",
        )
        logger.info("reindex_edges: merged note=%s edges=%d", note_id, len(edges))
        return {"status": "updated", "note_id": note_id, "edges": len(edges)}
    except Exception as exc:  # fail soft — never break the write path
        logger.exception("reindex_edges failed note=%s", note_id)
        return {"status": "error", "note_id": note_id, "error": str(exc)}
