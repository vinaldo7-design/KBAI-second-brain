"""mini-vinny must see graph changes the write-agent process makes, and the
graph file must never be readable half-written."""

import json
import os
import sys
from pathlib import Path

import pytest

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

import minivinnymcp.server as mv  # noqa: E402
import vault_graph  # noqa: E402


def _node(note_id):
    return {"id": note_id, "title": note_id, "type": "idea", "summary": "s"}


def _write(path, ids, tick):
    path.write_text(json.dumps({"vault_root": str(path.parent), "nodes": [_node(i) for i in ids], "edges": []}))
    os.utime(path, (tick, tick))


@pytest.fixture
def graph_file(tmp_path, monkeypatch):
    path = tmp_path / "vault-graph.json"
    _write(path, ["a"], 1000)
    monkeypatch.setattr(mv, "_GRAPH_PATH", path)
    monkeypatch.setattr(mv, "_graph", None)
    return path


def test_new_note_is_visible_after_the_file_changes(graph_file):
    assert not mv._get_graph().exists("b")
    _write(graph_file, ["a", "b"], 2000)
    assert mv._get_graph().exists("b")


def test_unchanged_file_is_not_reparsed(graph_file):
    assert mv._get_graph() is mv._get_graph()


def test_unreadable_update_keeps_the_last_good_graph(graph_file):
    assert mv._get_graph().exists("a")
    graph_file.write_text("{ not json")
    os.utime(graph_file, (3000, 3000))
    assert mv._get_graph().exists("a")


def test_write_graph_replaces_the_file(tmp_path):
    path = tmp_path / "g.json"
    vault_graph.write_graph({"nodes": ["é"]}, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"nodes": ["é"]}
    assert [p.name for p in tmp_path.iterdir()] == ["g.json"]


def test_failed_write_keeps_the_old_file_and_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "g.json"
    path.write_text("old")

    def boom(*_):
        raise OSError("disk full")

    monkeypatch.setattr(vault_graph.os, "replace", boom)
    with pytest.raises(OSError):
        vault_graph.write_graph({"nodes": []}, path)
    assert path.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["g.json"]
