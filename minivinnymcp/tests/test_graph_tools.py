import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from minivinnymcp.server import graph_expand, audit_taxonomy, get_note_with_context, assemble_context
from vault_graph_loader import VaultGraph

GRAPH_PATH = _vault_root / "06-Maps" / "vault-graph.json"


def _graph_available() -> bool:
    return GRAPH_PATH.exists()


# --- graph_expand ---

def test_graph_expand_returns_hops():
    if not _graph_available():
        return
    result = graph_expand("mastery-trap")
    assert "hops" in result
    assert "note_id" in result
    assert isinstance(result["hops"], list)


def test_graph_expand_hop_shape():
    if not _graph_available():
        return
    result = graph_expand("mastery-trap", max_hops=1)
    for hop in result["hops"]:
        assert {"note_id", "edge_type", "direction", "weight", "hop"} <= hop.keys()
        assert hop["hop"] == 1
        assert hop["direction"] in ("in", "out")
        assert isinstance(hop["weight"], float)


def test_graph_expand_sorted_by_weight():
    if not _graph_available():
        return
    result = graph_expand("mastery-trap", max_hops=1)
    weights = [h["weight"] for h in result["hops"]]
    assert weights == sorted(weights, reverse=True)


def test_graph_expand_unknown_note():
    if not _graph_available():
        return
    result = graph_expand("this-note-does-not-exist-xyz")
    assert "error" in result


# --- audit_taxonomy ---

def test_audit_taxonomy_returns_list():
    if not _graph_available():
        return
    result = audit_taxonomy("analogous-to", "exemplifies")
    assert isinstance(result, list)


def test_audit_taxonomy_result_shape():
    if not _graph_available():
        return
    result = audit_taxonomy("analogous-to", "exemplifies")
    if result and "error" not in result[0]:
        item = result[0]
        assert {"source", "target", "score", "source_summary", "target_summary"} <= item.keys()
        assert 0.0 <= item["score"] <= 1.0


def test_audit_taxonomy_sorted_descending():
    if not _graph_available():
        return
    result = audit_taxonomy("analogous-to", "exemplifies")
    scores = [r["score"] for r in result if "error" not in r]
    assert scores == sorted(scores, reverse=True)


def test_audit_taxonomy_bad_type():
    if not _graph_available():
        return
    result = audit_taxonomy("nonexistent-type", "exemplifies")
    assert len(result) == 1
    assert "error" in result[0]


# --- get_note_with_context ---

def test_get_note_with_context_shape():
    if not _graph_available():
        return
    result = get_note_with_context("mastery-trap")
    assert {"note_id", "title", "summary", "content", "edges"} <= result.keys()
    assert isinstance(result["edges"], list)


def test_get_note_with_context_edge_shape():
    if not _graph_available():
        return
    result = get_note_with_context("mastery-trap")
    for edge in result["edges"]:
        assert {"note_id", "edge_type", "direction"} <= edge.keys()
        assert edge["direction"] in ("in", "out")


def test_get_note_with_context_unknown():
    if not _graph_available():
        return
    result = get_note_with_context("this-note-does-not-exist-xyz")
    assert "error" in result


# --- assemble_context ---

def test_assemble_context_shape():
    if not _graph_available():
        return
    result = assemble_context("mastery and deliberate practice")
    assert {"query", "notes", "chars_used", "char_budget"} <= result.keys()
    assert isinstance(result["notes"], list)
    assert result["chars_used"] <= result["char_budget"]


def test_assemble_context_note_shape():
    if not _graph_available():
        return
    result = assemble_context("mastery and deliberate practice", seed_k=3)
    for note in result["notes"]:
        assert {"note_id", "composite_score", "source"} <= note.keys()
        assert note["source"] in ("seed", "ppr")


def test_assemble_context_sorted_by_score():
    if not _graph_available():
        return
    result = assemble_context("governance capital", seed_k=3)
    scores = [n["composite_score"] for n in result["notes"]]
    assert scores == sorted(scores, reverse=True)


def test_assemble_context_budget_respected():
    if not _graph_available():
        return
    result = assemble_context("mastery", char_budget=2000)
    assert result["chars_used"] <= 2000


def test_assemble_context_sparring_mode():
    if not _graph_available():
        return
    result = assemble_context("governance capital", seed_k=3, mode="sparring")
    assert {"query", "notes", "chars_used", "char_budget"} <= result.keys()
    assert isinstance(result["notes"], list)


def test_assemble_context_capped_at_50():
    if not _graph_available():
        return
    result = assemble_context("AI governance", seed_k=5)
    assert len(result["notes"]) <= 50


# --- ppr_expand ---

def test_ppr_expand_returns_all_nodes():
    if not _graph_available():
        return
    g = VaultGraph.load(str(GRAPH_PATH))
    seeds = {"mastery-trap": 0.9, "governance-capital-day1": 0.7}
    scores = g.ppr_expand(seeds)
    assert len(scores) == len(g.G.nodes)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


def test_ppr_expand_seeds_rank_high():
    if not _graph_available():
        return
    g = VaultGraph.load(str(GRAPH_PATH))
    seeds = {"mastery-trap": 1.0}
    scores = g.ppr_expand(seeds)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top_10 = [nid for nid, _ in ranked[:10]]
    assert "mastery-trap" in top_10


def test_ppr_expand_exclude_contradicts():
    if not _graph_available():
        return
    g = VaultGraph.load(str(GRAPH_PATH))
    seeds = {"mastery-trap": 1.0}
    standard = g.ppr_expand(seeds, exclude_types={"contradicts"})
    sparring = g.ppr_expand(seeds, exclude_types=set())
    # scores will differ when contradicts edges are included
    assert standard != sparring


def test_ppr_expand_empty_seeds():
    if not _graph_available():
        return
    g = VaultGraph.load(str(GRAPH_PATH))
    scores = g.ppr_expand({})
    assert isinstance(scores, dict)


# --- path_attributions ---

def test_path_attributions_returns_dict():
    if not _graph_available():
        return
    g = VaultGraph.load(str(GRAPH_PATH))
    result = g.path_attributions(
        seed_ids=["mastery-trap"],
        target_ids=["governance-capital-day1", "schumacher-principle"],
    )
    assert isinstance(result, dict)
    assert set(result.keys()) == {"governance-capital-day1", "schumacher-principle"}


def test_path_attributions_step_shape():
    if not _graph_available():
        return
    g = VaultGraph.load(str(GRAPH_PATH))
    result = g.path_attributions(
        seed_ids=["mastery-trap"],
        target_ids=["schumacher-principle"],
        max_hops=3,
    )
    path = result.get("schumacher-principle")
    if path:
        for step in path:
            assert {"from", "edge", "to"} <= step.keys()
            assert isinstance(step["edge"], str)


def test_path_attributions_respects_max_hops():
    if not _graph_available():
        return
    g = VaultGraph.load(str(GRAPH_PATH))
    result = g.path_attributions(
        seed_ids=["mastery-trap"],
        target_ids=["dag-directed-acyclic-graph"],
        max_hops=1,
    )
    path = result.get("dag-directed-acyclic-graph")
    assert path is None or len(path) <= 1


def test_path_attributions_prefers_semantic_edges():
    if not _graph_available():
        return
    g = VaultGraph.load(str(GRAPH_PATH))
    result = g.path_attributions(
        seed_ids=["zettelkasten-and-second-brain"],
        target_ids=["vault-as-cyclic-directed-graph"],
        max_hops=2,
    )
    path = result.get("vault-as-cyclic-directed-graph")
    if path:
        for step in path:
            assert step["edge"] not in ("referenced-in", "untyped", "mentioned")


# --- assemble_context reasoning_path and note_hits ---

def test_assemble_context_has_reasoning_path():
    if not _graph_available():
        return
    result = assemble_context("governance capital", seed_k=3)
    for note in result["notes"]:
        assert "reasoning_path" in note
        if note["source"] == "ppr" and note["reasoning_path"] is not None:
            for step in note["reasoning_path"]:
                assert {"from", "edge", "to"} <= step.keys()


def test_note_hits_table_created():
    import sqlite3, os
    if not _graph_available():
        return
    assemble_context("mastery trap", seed_k=3)
    db_path = _vault_root / "06-Maps" / "vault-embeddings.db"
    db = sqlite3.connect(db_path)
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    db.close()
    assert "note_hits" in tables
