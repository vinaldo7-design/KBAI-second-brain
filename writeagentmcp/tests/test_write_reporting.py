"""A write that lands but is not indexed or journalled must say so, and must not
stop a batch. Hooks and the journal are replaced; the real vault is never touched."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.storage import link_applier, note_creator, post_write  # noqa: E402

FM = {
    "id": "202610300001",
    "title": "T",
    "created": "2026-10-30",
    "updated": "2026-10-30",
    "type": "idea",
    "status": "seedling",
    "summary": "S.",
    "tags": ["topic/governance", "lens/strategic"],
}
NOTE = "---\nid: 1\ntitle: N\n---\n\n# N\n\n## Links\n\n### Builds on\n"


def _hooks(monkeypatch, embed="embedded", graph="updated"):
    seen = []

    def hook(status):
        def run(note_id, vault_root=None):
            seen.append(vault_root)
            return {"status": status, "note_id": note_id, "error": "boom"}
        return run

    monkeypatch.setattr(post_write, "update_note_embeddings", hook(embed))
    monkeypatch.setattr(post_write, "update_note_edges", hook(graph))
    return seen


def _broken_journal(**_):
    raise sqlite3.OperationalError("database is locked")


def _create(tmp_path):
    return note_creator.create_note(tmp_path, "01-Ideas", "x", dict(FM), "body")


def test_create_reports_index_status_when_healthy(tmp_path, monkeypatch):
    _hooks(monkeypatch)
    r = _create(tmp_path)
    assert r.status == "applied"
    assert r.index_status == {"embeddings": "embedded", "graph": "updated"}
    assert r.message is None


def test_create_warns_when_the_note_is_not_indexed(tmp_path, monkeypatch):
    _hooks(monkeypatch, embed="error")
    r = _create(tmp_path)
    assert r.status == "applied" and r.applied
    assert r.index_status["embeddings"] == "error"
    assert "not indexed" in r.message and "boom" in r.message


def test_create_survives_a_journal_failure(tmp_path, monkeypatch):
    _hooks(monkeypatch)
    monkeypatch.setattr(post_write, "record_mutation", _broken_journal)
    r = _create(tmp_path)
    assert r.applied and r.journal_id is None
    assert "journal" in r.message and "locked" in r.message
    assert (tmp_path / "01-Ideas" / "x.md").exists()


def _two_notes(tmp_path):
    (tmp_path / "01-Ideas").mkdir()
    for name in ("a", "b"):
        (tmp_path / "01-Ideas" / f"{name}.md").write_text(NOTE)
    return [
        {"source_id": "a", "target_id": "z", "edge_type": "builds-on"},
        {"source_id": "b", "target_id": "z", "edge_type": "builds-on"},
    ]


def test_links_pass_the_vault_root_to_the_hooks(tmp_path, monkeypatch):
    seen = _hooks(monkeypatch)
    monkeypatch.setattr(post_write, "record_mutation", lambda **_: 1)
    link_applier.apply_link_suggestions(tmp_path, _two_notes(tmp_path))
    assert seen and all(root == tmp_path for root in seen)


def test_journal_failure_does_not_stop_a_link_batch(tmp_path, monkeypatch):
    _hooks(monkeypatch)
    monkeypatch.setattr(post_write, "record_mutation", _broken_journal)
    r = link_applier.apply_link_suggestions(tmp_path, _two_notes(tmp_path))
    assert r.applied_count == 2
    assert all(row["journal_id"] is None and "locked" in row["journal_error"] for row in r.results)
    assert "journal" in r.message


def test_link_batch_reports_index_failures(tmp_path, monkeypatch):
    _hooks(monkeypatch, graph="error")
    monkeypatch.setattr(post_write, "record_mutation", lambda **_: 1)
    r = link_applier.apply_link_suggestions(tmp_path, _two_notes(tmp_path))
    assert all(row["index_status"]["graph"] == "error" for row in r.results)
    assert "not indexed" in r.message


def test_healthy_link_batch_has_no_message(tmp_path, monkeypatch):
    _hooks(monkeypatch)
    monkeypatch.setattr(post_write, "record_mutation", lambda **_: 1)
    assert link_applier.apply_link_suggestions(tmp_path, _two_notes(tmp_path)).message is None


def test_write_agent_refuses_to_start_without_a_vault_root():
    env = {k: v for k, v in os.environ.items() if k != "VAULT_ROOT"}
    env["PYTHONPATH"] = str(_vault_root)
    result = subprocess.run(
        [sys.executable, "-c", "import writeagentmcp.server"],
        capture_output=True, text=True, env=env, cwd=_vault_root, timeout=120,
    )
    assert result.returncode != 0
    assert "VAULT_ROOT" in result.stderr
