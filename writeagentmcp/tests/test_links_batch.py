"""The batch link command: reasons kept, mirrors written, nothing applied unless the
whole list is valid. Runs on a throwaway vault."""

import json

import pytest

from kbai import links
from kbai.storage.section_patcher import patch_section


def _note(vault, note_id):
    return (vault / "01-Ideas" / f"{note_id}.md").read_text(encoding="utf-8")


def _entry(source="rotate-metrics-quarterly", target="managed-metrics-hold", kind="builds-on", why="a reason"):
    return {"source": source, "target": target, "type": kind, "why": why}


def test_patch_section_stores_the_reason():
    text, status = patch_section("# N\n\n### Builds on\n- [[a]]\n", "builds-on", "b", why="because b")
    assert status == "patched"
    assert "- [[b]]: because b\n" in text


def test_patch_section_adds_a_reason_to_a_bare_link():
    text, status = patch_section("# N\n\n### Builds on\n- [[a]]\n- [[c]]\n", "builds-on", "a", why="because a")
    assert status == "patched"
    assert "- [[a]]: because a\n- [[c]]\n" in text


def test_patch_section_keeps_an_existing_reason():
    source = "# N\n\n### Builds on\n- [[a]]: original\n"
    assert patch_section(source, "builds-on", "a", why="new") == (source, "already_present")


def test_reason_is_stored_on_the_link_and_in_the_graph(toy_vault):
    report = links.apply_links([_entry()], toy_vault)
    assert report.problems == []
    assert "- [[managed-metrics-hold]]: a reason" in _note(toy_vault, "rotate-metrics-quarterly")
    graph = json.loads((toy_vault / "06-Maps" / "vault-graph.json").read_text(encoding="utf-8"))
    edge = next(
        e for e in graph["edges"]
        if e["source"] == "rotate-metrics-quarterly" and e["target"] == "managed-metrics-hold"
    )
    assert edge["annotation"] == "a reason"


@pytest.mark.parametrize(
    "kind, mirror, heading",
    [
        ("builds-on", "builds-toward", "### Builds toward"),
        ("builds-toward", "builds-on", "### Builds on"),
        ("contradicts", "contradicts", "### Contradicts"),
        ("analogous-to", "analogous-to", "### Analogous to"),
    ],
)
def test_two_way_types_get_a_mirror_line(toy_vault, kind, mirror, heading):
    links.apply_links([_entry(kind=kind)], toy_vault)
    assert heading in _note(toy_vault, "managed-metrics-hold")
    assert "- [[rotate-metrics-quarterly]]: a reason" in _note(toy_vault, "managed-metrics-hold")


@pytest.mark.parametrize("kind", ["challenges", "exemplifies", "operationalises"])
def test_one_way_types_get_no_mirror(toy_vault, kind):
    before = _note(toy_vault, "managed-metrics-hold")
    links.apply_links([_entry(kind=kind)], toy_vault)
    assert _note(toy_vault, "managed-metrics-hold") == before


@pytest.mark.parametrize(
    "bad, expected",
    [
        (_entry(target="no-such-note"), "no-such-note"),
        (_entry(source="no-such-note"), "no-such-note"),
        (_entry(kind="inspires"), "inspires"),
        (_entry(target="rotate-metrics-quarterly"), "itself"),
        ({"source": "rotate-metrics-quarterly"}, "missing"),
        (_entry(why=""), "why"),
    ],
)
def test_one_bad_entry_stops_the_whole_batch(toy_vault, bad, expected):
    before = _note(toy_vault, "rotate-metrics-quarterly")
    report = links.apply_links([_entry(), bad], toy_vault)
    assert report.applied == 0
    assert any(expected in p for p in report.problems)
    assert _note(toy_vault, "rotate-metrics-quarterly") == before


def test_dry_run_writes_nothing_but_reports_the_lines(toy_vault):
    before = _note(toy_vault, "rotate-metrics-quarterly")
    report = links.apply_links([_entry()], toy_vault, dry_run=True)
    assert report.planned == 2 and report.applied == 0
    assert _note(toy_vault, "rotate-metrics-quarterly") == before


def test_rerunning_a_batch_changes_nothing(toy_vault):
    links.apply_links([_entry()], toy_vault)
    report = links.apply_links([_entry()], toy_vault)
    assert report.applied == 0 and report.already_present == 2


def test_warns_about_a_pair_that_already_has_another_type(toy_vault):
    report = links.apply_links([_entry(source="metric-targets-decay", target="incentives-shape-behaviour", kind="exemplifies")], toy_vault)
    assert any("already linked" in w for w in report.warnings)


def test_a_failed_audit_is_reported(toy_vault, monkeypatch):
    monkeypatch.setattr(links, "run_audit", lambda root: "RESULT: FAIL")
    report = links.apply_links([_entry()], toy_vault)
    assert any("audit" in p and "FAIL" in p for p in report.problems)


def test_healthy_batch_passes_the_real_audit(toy_vault):
    assert links.apply_links([_entry()], toy_vault).problems == []
