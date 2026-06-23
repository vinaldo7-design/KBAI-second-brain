"""Graph-side freshness (improvement): the per-note edge reindex hook must keep
06-Maps/vault-graph.json current on write WITHOUT a full vault walk — and the
result must equal what a full rebuild would produce.

TDD parity test (objective, no golden set needed): create a note that an existing
note already links to (a dangling edge), run the incremental hook, and assert the
graph's nodes+edges match a full `vault_graph.build_graph` rebuild — including the
dangling edge now resolving to target_exists=True. Compared order-independently
(graph semantics don't depend on list order); both sides JSON-normalised so dates
serialise identically.
"""

import json
import os
import shutil
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

import vault_graph  # noqa: E402
from kbai.graph.reindex_hooks import update_note_edges  # noqa: E402


def _fm(note_id: str, title: str, ntype: str = "idea") -> str:
    return (
        f"---\nid: '{note_id}'\ntitle: {title}\ncreated: 2026-06-23\n"
        f"updated: 2026-06-23\ntype: {ntype}\nstatus: seedling\nsummary: a summary\n"
        f"tags:\n  - topic/x\n  - lens/academic\n---\n\n# {title}\n"
    )


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _setup(tmp_path: Path) -> Path:
    shutil.copy(_vault_root / "vault_taxonomy.yaml", tmp_path / "vault_taxonomy.yaml")
    (tmp_path / "06-Maps").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _norm(graph: dict) -> dict:
    """JSON round-trip so datetime.date serialises to str on both sides."""
    return json.loads(json.dumps(graph, default=vault_graph._json_default))


def _nodes_by_id(graph: dict) -> dict:
    return {n["id"]: n for n in graph["nodes"]}


def _edges_set(graph: dict) -> set:
    return {
        (e["source"], e["target"], e["type"], e["target_exists"])
        for e in graph["edges"]
    }


def test_incremental_edge_update_matches_full_rebuild(tmp_path):
    vault = _setup(tmp_path)
    graph_path = vault / "06-Maps" / "vault-graph.json"

    # Existing note `b` links to `x`, which does not exist yet → dangling edge.
    _write(vault / "01-Ideas" / "b.md",
           _fm("202606231200", "B") + "\n## Links\n\n### Builds on\n- [[x]]\n")

    # Baseline graph on disk (x absent → b→x is broken).
    baseline = vault_graph.build_graph(vault)
    graph_path.write_text(json.dumps(baseline, default=vault_graph._json_default, indent=2))
    assert ("b", "x", "builds-on", False) in _edges_set(_norm(baseline))

    # Now create x (it links back to b).
    _write(vault / "01-Ideas" / "x.md",
           _fm("202606231201", "X") + "\n## Links\n\n### Builds on\n- [[b]]\n")

    # Incremental hook — must NOT walk the whole vault, just reparse x and merge.
    result = update_note_edges("x", vault)
    assert result["status"] == "updated", result

    incr = json.loads(graph_path.read_text())
    full = _norm(vault_graph.build_graph(vault))

    # Parity: same node set, same edge set (order-independent).
    assert _nodes_by_id(incr).keys() == _nodes_by_id(full).keys()
    assert "x" in _nodes_by_id(incr)
    assert _edges_set(incr) == _edges_set(full), (
        f"incremental != full rebuild\n only-incr={_edges_set(incr) - _edges_set(full)}\n"
        f" only-full={_edges_set(full) - _edges_set(incr)}"
    )
    # The previously-dangling edge now resolves.
    assert ("b", "x", "builds-on", True) in _edges_set(incr)


def test_hook_no_graph_is_soft_skip(tmp_path):
    # No graph file yet → soft skip, never raises.
    vault = _setup(tmp_path)
    out = update_note_edges("anything", vault)
    assert out["status"] in ("skipped", "error")
    assert out["status"] == "skipped"


def test_hook_rejects_empty_note_id():
    assert update_note_edges("")["status"] == "error"
