import pytest
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent

from minivinnymcp.server import graph_expand, audit_taxonomy, notes_get_with_context, retrieve_assemble
from vault_graph_loader import VaultGraph

GRAPH_PATH = _vault_root / "06-Maps" / "vault-graph.json"


def _graph_available() -> bool:
    return GRAPH_PATH.exists()


# --- graph_expand ---

@pytest.mark.live
def test_graph_expand_returns_hops():
    result = graph_expand("mastery-trap")
    assert "hops" in result
    assert "note_id" in result
    assert isinstance(result["hops"], list)


@pytest.mark.live
def test_graph_expand_hop_shape():
    result = graph_expand("mastery-trap", max_hops=1)
    for hop in result["hops"]:
        assert {"note_id", "edge_type", "direction", "weight", "hop"} <= hop.keys()
        assert hop["hop"] == 1
        assert hop["direction"] in ("in", "out")
        assert isinstance(hop["weight"], float)


@pytest.mark.live
def test_graph_expand_sorted_by_weight():
    result = graph_expand("mastery-trap", max_hops=1)
    weights = [h["weight"] for h in result["hops"]]
    assert weights == sorted(weights, reverse=True)


@pytest.mark.live
def test_graph_expand_unknown_note():
    result = graph_expand("this-note-does-not-exist-xyz")
    assert "error" in result


# --- audit_taxonomy ---

@pytest.mark.live
def test_audit_taxonomy_returns_list():
    result = audit_taxonomy("analogous-to", "exemplifies")
    assert isinstance(result, list)


@pytest.mark.live
def test_audit_taxonomy_result_shape():
    result = audit_taxonomy("analogous-to", "exemplifies")
    assert result and "error" not in result[0]
    item = result[0]
    assert {"source", "target", "score", "source_summary", "target_summary"} <= item.keys()
    assert 0.0 <= item["score"] <= 1.0


@pytest.mark.live
def test_audit_taxonomy_sorted_descending():
    result = audit_taxonomy("analogous-to", "exemplifies")
    scores = [r["score"] for r in result if "error" not in r]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.live
def test_audit_taxonomy_bad_type():
    result = audit_taxonomy("nonexistent-type", "exemplifies")
    assert len(result) == 1
    assert "error" in result[0]


# --- notes_get_with_context ---

@pytest.mark.live
def test_get_note_with_context_shape():
    result = notes_get_with_context("mastery-trap")
    assert {"note_id", "title", "summary", "content", "edges"} <= result.keys()
    assert isinstance(result["edges"], list)


@pytest.mark.live
def test_get_note_with_context_edge_shape():
    result = notes_get_with_context("mastery-trap")
    for edge in result["edges"]:
        assert {"note_id", "edge_type", "direction"} <= edge.keys()
        assert edge["direction"] in ("in", "out")


@pytest.mark.live
def test_get_note_with_context_unknown():
    result = notes_get_with_context("this-note-does-not-exist-xyz")
    assert "error" in result


# --- retrieve_assemble ---

@pytest.mark.live
def test_assemble_context_shape():
    result = retrieve_assemble("mastery and deliberate practice")
    assert {"query", "notes", "chars_used", "char_budget"} <= result.keys()
    assert isinstance(result["notes"], list)
    assert result["chars_used"] <= result["char_budget"]


@pytest.mark.live
def test_assemble_context_note_shape():
    result = retrieve_assemble("mastery and deliberate practice", seed_k=3)
    for note in result["notes"]:
        assert {"note_id", "composite_score", "source"} <= note.keys()
        assert note["source"] in ("seed", "ppr")


@pytest.mark.live
def test_assemble_context_returns_scored_notes():
    result = retrieve_assemble("governance capital", seed_k=3)
    notes = result["notes"]
    assert notes, "expected at least one note"
    # Every note carries its first-stage PPR composite_score. The FINAL order is
    # now set by the cross-encoder reranker (mode path), so the list is no longer
    # monotonic in composite_score — assert presence/type, not sort order.
    assert all(isinstance(n["composite_score"], (int, float)) for n in notes)


@pytest.mark.live
def test_assemble_context_budget_respected():
    result = retrieve_assemble("mastery", char_budget=2000)
    assert result["chars_used"] <= 2000


@pytest.mark.live
def test_assemble_context_sparring_mode():
    result = retrieve_assemble("governance capital", seed_k=3, mode="sparring")
    assert {"query", "notes", "chars_used", "char_budget"} <= result.keys()
    assert isinstance(result["notes"], list)


@pytest.mark.live
def test_assemble_context_capped_at_50():
    result = retrieve_assemble("AI governance", seed_k=5)
    assert len(result["notes"]) <= 50


# --- ppr_expand ---

@pytest.mark.live
def test_ppr_expand_returns_all_nodes():
    g = VaultGraph.load(str(GRAPH_PATH))
    seeds = {"mastery-trap": 0.9, "governance-capital-day1": 0.7}
    scores = g.ppr_expand(seeds)
    # PPR walks the default view, not raw self.G. Scores must cover every node
    # the view exposes — that includes all real notes plus in-view broken markers.
    assert len(scores) == len(g.view().nodes)
    assert all(0.0 <= v <= 1.0 for v in scores.values())


@pytest.mark.live
def test_ppr_expand_seeds_rank_high():
    g = VaultGraph.load(str(GRAPH_PATH))
    seeds = {"mastery-trap": 1.0}
    scores = g.ppr_expand(seeds)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    top_10 = [nid for nid, _ in ranked[:10]]
    assert "mastery-trap" in top_10


@pytest.mark.live
def test_ppr_expand_exclude_contradicts():
    g = VaultGraph.load(str(GRAPH_PATH))
    seeds = {"mastery-trap": 1.0}
    standard = g.ppr_expand(seeds, exclude_types={"contradicts"})
    sparring = g.ppr_expand(seeds, exclude_types=set())
    # scores will differ when contradicts edges are included
    assert standard != sparring


@pytest.mark.live
def test_ppr_expand_empty_seeds():
    g = VaultGraph.load(str(GRAPH_PATH))
    scores = g.ppr_expand({})
    assert isinstance(scores, dict)


# --- path_attributions ---

@pytest.mark.live
def test_path_attributions_returns_dict():
    g = VaultGraph.load(str(GRAPH_PATH))
    result = g.path_attributions(
        seed_ids=["mastery-trap"],
        target_ids=["governance-capital-day1", "schumacher-principle"],
    )
    assert isinstance(result, dict)
    assert set(result.keys()) == {"governance-capital-day1", "schumacher-principle"}


@pytest.mark.live
def test_path_attributions_step_shape():
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


@pytest.mark.live
def test_path_attributions_respects_max_hops():
    g = VaultGraph.load(str(GRAPH_PATH))
    result = g.path_attributions(
        seed_ids=["mastery-trap"],
        target_ids=["dag-directed-acyclic-graph"],
        max_hops=1,
    )
    path = result.get("dag-directed-acyclic-graph")
    assert path is None or len(path) <= 1


@pytest.mark.live
def test_path_attributions_prefers_semantic_edges():
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


# --- retrieve_assemble reasoning_path and note_hits ---

@pytest.mark.live
def test_assemble_context_has_reasoning_path():
    result = retrieve_assemble("governance capital", seed_k=3)
    for note in result["notes"]:
        assert "reasoning_path" in note
        if note["source"] == "ppr" and note["reasoning_path"] is not None:
            for step in note["reasoning_path"]:
                assert {"from", "edge", "to"} <= step.keys()


