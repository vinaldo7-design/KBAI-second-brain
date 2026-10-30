"""The whole read and write path, through the public tools, on a throwaway vault."""

import json

import minivinnymcp.server as mv
import vault_graph
from kbai.storage.link_applier import apply_link_suggestions
from kbai.storage.note_creator import create_note


def _ids(result):
    return [n["note_id"] for n in result["notes"]]


def _edges_walked(result):
    return {step["edge"] for n in result["notes"] for step in n["reasoning_path"] or []}


def test_search_finds_the_note_that_shares_the_words(toy_vault):
    hits = mv.retrieve_search("rotate metrics quarterly", top_k=2)
    assert hits[0]["note_id"] == "rotate-metrics-quarterly"


def test_assemble_follows_links_but_not_contradictions_by_default(toy_vault):
    result = mv.retrieve_assemble("metric targets decay", seed_k=1)
    assert _ids(result)[0] == "metric-targets-decay"
    assert "builds-on" in _edges_walked(result)
    assert "contradicts" not in _edges_walked(result)


def test_sparring_walks_the_contradiction(toy_vault):
    result = mv.retrieve_assemble("metric targets decay", seed_k=1, mode="sparring")
    assert "contradicts" in _edges_walked(result)


def test_get_note_returns_content_and_typed_neighbours(toy_vault):
    note = mv.notes_get_with_context("metric-targets-decay")
    assert "Metric targets decay" in note["content"]
    assert "incentives-shape-behaviour" in json.dumps(note)


def test_missing_note_reports_an_error(toy_vault):
    assert "error" in mv.notes_get_with_context("no-such-note")


def test_graph_expand_reaches_a_neighbour(toy_vault):
    assert "incentives-shape-behaviour" in json.dumps(mv.graph_expand("metric-targets-decay", max_hops=1))


def test_audit_scores_every_edge_of_the_type(toy_vault):
    rows = mv.audit_taxonomy("operationalises", "exemplifies")
    assert [(r["source"], r["target"]) for r in rows] == [("rotate-metrics-quarterly", "metric-targets-decay")]


def test_council_returns_one_result_per_lens(toy_vault):
    evidence = mv.council_retrieve("metric targets decay", top_k=3)
    assert len(evidence["per_profile"]) == 3


def test_a_created_note_is_searchable_and_readable_at_once(toy_vault):
    fm = {
        "id": "202610300099", "title": "Fresh", "created": "2026-10-30", "updated": "2026-10-30",
        "type": "idea", "status": "seedling", "summary": "Zebra crossings slow traffic.",
        "tags": ["topic/test", "lens/strategic"],
    }
    mv._get_graph()
    receipt = create_note(toy_vault, "01-Ideas", "zebra-crossings", fm, "body")
    assert receipt.index_status == {"embeddings": "embedded", "graph": "updated"}
    assert mv.retrieve_search("zebra crossings", top_k=1)[0]["note_id"] == "zebra-crossings"
    assert mv.notes_get_with_context("zebra-crossings")["content"]


def test_an_added_link_reaches_the_graph(toy_vault):
    mv._get_graph()
    receipt = apply_link_suggestions(toy_vault, [
        {"source_id": "managed-metrics-hold", "target_id": "rotate-metrics-quarterly", "edge_type": "builds-on"},
    ])
    assert receipt.applied_count == 1
    assert "rotate-metrics-quarterly" in json.dumps(mv.notes_get_with_context("managed-metrics-hold"))


def test_graph_ignores_hidden_folders(toy_vault):
    hidden = toy_vault / ".venv" / "lib"
    hidden.mkdir(parents=True)
    (hidden / "LICENSE.md").write_text("# License\n")
    ids = {node["id"] for node in vault_graph.build_graph(toy_vault)["nodes"]}
    assert "LICENSE" not in ids and "metric-targets-decay" in ids
